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

def count_atfd_method(method_code):
    """Menghitung akses ke atribut kelas lain dalam suatu metode."""
    import re
    # Pola regex untuk mendeteksi 'obj.atribut' (hindari 'this.' atau 'super.')
    pattern = r'\b(\w+)\.(\w+)\b(?![ \t]*\()'  # Hindari pemanggilan method (seperti 'obj.method()')
    matches = re.findall(pattern, method_code)
    # Filter out 'this' atau 'super' sebagai objek
    filtered = [m for m in matches if m[0] not in ['this', 'super']]
    return len(filtered)

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

def extracted_method(file_path):
    """Ekstrak informasi metode dari file Kotlin, termasuk ATFD_type dan FANOUT_type."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        parser = Parser(code)
        result = parser.parse()
        package_name = result.package.name if result.package else "Unknown"

        if not result.declarations:
            return [{"Package": package_name, "Class": "Unknown", "Method": "None", "LOC": 0, "Max Nesting": 0, "CC": 0, "WOC": 0, "ATFD_type": 0, "FANOUT_type": 0, "Error": "No class declaration found"}]
        
        class_declaration = result.declarations[0]
        class_name = class_declaration.name
        
        if class_declaration.body is None:
            return [{"Package": package_name, "Class": class_name, "Method": "None", "LOC": 0, "Max Nesting": 0, "CC": 0, "WOC": 0, "ATFD_type": 0, "FANOUT_type": 0, "Error": "Class has no body"}]
        
        datas = []
        method_function = {}
        atfd_total = 0  # Total ATFD untuk seluruh kelas
        fanout_total = count_fanout(code)  # Hitung FANOUT_type untuk kelas ini
        
        for member in class_declaration.body.members:
            if isinstance(member, node.FunctionDeclaration):
                function_names = member.name
                loc_count = str(member.body).count("\n") + 1 if member.body else 0
                maxnesting = manual_max_nesting(str(member.body)) if member.body else 0
                cc_value = count_cc_manual(str(member.body)) if member.body else 0
                method_code = str(member.body) if member.body else ""
                atfd_method = count_atfd_method(method_code)
                atfd_total += atfd_method  # Akumulasi total ATFD
                method_function[function_names] = (cc_value, loc_count, maxnesting)

        cc_values = [cc for cc, _, _ in method_function.values()]
        woc_values = count_woc(cc_values)

        for (function_names, (cc_value, loc_count, maxnesting)), woc in zip(method_function.items(), woc_values):
            datas.append({
                "Package": package_name,
                "Class": class_name,
                "Method": function_names,
                "LOC": loc_count,
                "Max Nesting": maxnesting,
                "CC": cc_value,
                "WOC": woc,
                "ATFD_type": atfd_total,  # Tambahkan ATFD_type (total per kelas)
                "FANOUT_type": fanout_total,  # Tambahkan FANOUT_type (total per kelas)
                "Error": ""
            })
        
        return datas if datas else [{"Package": package_name, "Class": class_name, "Method": "None", "LOC": 0, "Max Nesting": 0, "CC": 0, "WOC": 0, "ATFD_type": 0, "FANOUT_type": 0, "Error": "No functions found"}]
    
    except Exception as e:
        return [{"Package": "Error", "Class": "Error", "Method": "Error", "LOC": "Error", "Max Nesting": 0, "CC": 0, "WOC": 0, "ATFD_type": 0, "FANOUT_type": 0, "Error": str(e)}]

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
