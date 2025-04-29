import os
import tempfile
import patoolib
import pandas as pd
from kopyt import Parser, node  # Gunakan `kopyt` sebagai parser AST Kotlin

def manual_max_nesting(body_str):
    """ Menghitung max nesting secara manual dari string kode """
    indent_levels = []
    max_depth = 0

    for line in body_str.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("if", "try", "for", "catch", "else", "when")):
            indent_levels.append(stripped)
            max_depth = max(max_depth, len(indent_levels))
        elif stripped == "}":
            if indent_levels:
                indent_levels.pop()
    
    return max_depth

def count_cc_manual(method_code):
    """
    Menghitung Cyclomatic Complexity (CC) secara manual dari string kode.
    """
    cc = 1  # Mulai dari 1 karena setiap metode memiliki setidaknya satu jalur

    # Daftar kata kunci yang menambah CC
    control_keywords = ["if", "for", "while", "when", "catch", "case"]

    # Memisahkan kode menjadi baris-baris
    lines = method_code.split("\n")

    for line in lines:
        stripped = line.strip()
        # Menghitung struktur kontrol
        for keyword in control_keywords:
            if stripped.startswith(keyword):
                cc += 1  # Setiap struktur kontrol menambah CC
    return cc

def count_woc(cc_values):
    """Menghitung Weighted Operations Count (WOC)."""
    total_CC = sum(cc_values)
    return [cc / total_CC if total_CC else 0 for cc in cc_values]

def count_atfd_type(class_declaration):
    """
    Menghitung ATFD_type (Access to Foreign Data) untuk sebuah kelas Kotlin.
    Versi yang lebih robust dengan penanganan error.
    """
    atfd = 0
    try:
        if class_declaration.body is None:
            return 0
        
        class_name = class_declaration.name
        for member in class_declaration.body.members:
            if isinstance(member, node.FunctionDeclaration) and member.body:
                body_str = str(member.body) if member.body else ""
                if not body_str:
                    continue
                
                # Deteksi akses ke atribut kelas lain dengan pendekatan yang lebih aman
                lines = body_str.split('\n')
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    
                    # Deteksi pola: identifier.identifier (tapi bukan this. atau super.)
                    if '.' in stripped and not stripped.startswith(('this.', 'super.')):
                        parts = stripped.split('.')
                        if len(parts) > 1:
                            receiver = parts[0].strip()
                            # Pastikan receiver adalah identifier valid dan bukan kelas sendiri
                            if (receiver and receiver[0].islower() and 
                                receiver != class_name and
                                not any(c in receiver for c in '(){}[]')):
                                atfd += 1
    except Exception as e:
        print(f"Error in count_atfd_type: {str(e)}")
        return 0
    
    return atfd

def count_fanout(class_code):
    """Menghitung jumlah kelas lain yang digunakan oleh kelas ini (FANOUT_type)."""
    import re
    # Pola regex untuk mendeteksi penggunaan kelas lain (misal: 'ClassName.method()' atau 'ClassName()')
    pattern = r'\b([A-Z][a-zA-Z0-9_]*)\b(?=\s*\.|\s*\()'
    matches = re.findall(pattern, class_code)
    # Filter out keyword Kotlin (seperti 'if', 'for', 'while') dan nama kelas sendiri
    keywords = ['if', 'for', 'while', 'when', 'try', 'catch', 'else', 'this', 'super']
    filtered = [m for m in matches if m not in keywords and not m[0].islower()]
    # Menghapus duplikat dan mengembalikan jumlah kelas unik
    unique_classes = set(filtered)
    return len(unique_classes)

def is_accessor_or_mutator(method_name, method_code):
    """
    Menentukan apakah suatu metode adalah accessor (getter) atau mutator (setter).
    """
    # Cek nama metode
    if method_name.startswith(("get", "is", "has")):  # Accessor (getter)
        return True
    if method_name.startswith("set"):  # Mutator (setter)
        return True
    
    # Cek logika sederhana: jika metode hanya mengembalikan nilai atau mengubah satu nilai
    if "return" in method_code and "=" not in method_code:  # Accessor
        return True
    if "=" in method_code and "return" not in method_code:  # Mutator
        return True
    
    return False

def count_noa_type(class_declaration):
    """Menghitung jumlah atribut dalam sebuah kelas (NOA_type)."""
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        return 0
    
    attribute_count = 0
    for member in class_declaration.body.members:
        if isinstance(member, node.PropertyDeclaration) or \
           (isinstance(member, node.VariableDeclaration) and not hasattr(member, 'function')):
            attribute_count += 1
    return attribute_count

def extracted_method(file_path):
    """Ekstrak informasi metode dari file Kotlin, termasuk ATFD_type, FANOUT_type, dan NOMNAMM_type."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        parser = Parser(code)
        result = parser.parse()
        package_name = result.package.name if result.package else "Unknown"

        if not result.declarations:
            return [{"Package": package_name, "Class": "Unknown", "Method": "None", "LOC": 0, "Max Nesting": 0, "CC": 0, "WOC": 0, "ATFD_type": 0, "FANOUT_type": 0, "NOA_type": 0, "Error": "No class declaration found"}]
        
        class_declaration = result.declarations[0]
        class_name = class_declaration.name
        
        if class_declaration.body is None:
            return [{"Package": package_name, "Class": class_name, "Method": "None", "LOC": 0, "Max Nesting": 0, "CC": 0, "WOC": 0, "ATFD_type": 0, "FANOUT_type": 0, "NOA_type": 0, "Error": "Class has no body"}]
        
        datas = []
        method_function = {}
        
        # Hitung metrik tingkat kelas sekali saja
        atfd_total = count_atfd_type(class_declaration)  # Pindahkan ke sini
        fanout_total = count_fanout(code)
        noa_total = count_noa_type(class_declaration)
        
        for member in class_declaration.body.members:
            if isinstance(member, node.FunctionDeclaration):
                try:
                    function_name = member.name
                    body_str = str(member.body) if member.body else ""
                    
                    loc_count = body_str.count('\n') + 1 if body_str else 0
                    maxnesting = manual_max_nesting(body_str) if body_str else 0
                    cc_value = count_cc_manual(body_str) if body_str else 0
                    
                    method_function[function_name] = (cc_value, loc_count, maxnesting)
                except Exception as e:
                    print(f"Error processing method {getattr(member, 'name', 'unknown')}: {str(e)}")
                    continue

        cc_values = [cc for cc, _, _ in method_function.values()]
        woc_values = count_woc(cc_values)

        for (function_name, (cc_value, loc_count, maxnesting)), woc in zip(method_function.items(), woc_values):
            datas.append({
                "Package": package_name,
                "Class": class_name,
                "Method": function_name,
                "LOC": loc_count,
                "Max Nesting": maxnesting,
                "CC": cc_value,
                "WOC": woc,
                "ATFD_type": atfd_total,  # Gunakan nilai yang sudah dihitung
                "FANOUT_type": fanout_total,
                "NOA_type": noa_total,
                "Error": ""
            })
        
        return datas if datas else [{
            "Package": package_name,
            "Class": class_name,
            "Method": "None",
            "LOC": 0,
            "Max Nesting": 0,
            "CC": 0,
            "WOC": 0,
            "ATFD_type": atfd_total,
            "FANOUT_type": fanout_total,
            "NOA_type": noa_total,
            "Error": "No functions found" if class_declaration.body.members else "Class has no members"
        }]
    
    except Exception as e:
        return [{
            "Package": "Error",
            "Class": "Error",
            "Method": "Error",
            "LOC": 0,
            "Max Nesting": 0,
            "CC": 0,
            "WOC": 0,
            "ATFD_type": 0,
            "FANOUT_type": 0,
            "NOA_type": 0,
            "Error": str(e)
        }]


def extract_and_parse(file):
    """Ekstrak arsip ZIP/RAR dan proses file Kotlin."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = os.path.join(temp_dir, file.name)
        with open(temp_file_path, "wb") as f:
            f.write(file.getbuffer())
        
        try:
            patoolib.extract_archive(temp_file_path, outdir=temp_dir)
            kotlin_files = [os.path.join(root, f) for root, _, files in os.walk(temp_dir) for f in files if f.endswith(".kt") or f.endswith(".kts")]
            
            results = []
            for kotlin_file in kotlin_files:
                results.extend(extracted_method(kotlin_file))
            
            return pd.DataFrame(results)
        except Exception as e:
            return str(e)
