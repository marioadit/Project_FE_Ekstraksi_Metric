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

def count_nomnamm_type(class_declaration):
    """
    Menghitung jumlah metode yang bukan accessor/mutator (NOMNAMM_type).
    Lebih akurat dengan memfilter berdasarkan body method yang hanya mengakses properti.
    """
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        return 0
    
    nomnamm_count = 0

    class_properties = set()

    # Ambil semua nama property untuk deteksi akses di getter/setter
    for member in class_declaration.body.members:
        if isinstance(member, node.PropertyDeclaration):
            decl = getattr(member, 'declaration', None)
            if isinstance(decl, node.VariableDeclaration):
                class_properties.add(decl.name)
            elif isinstance(decl, node.MultiVariableDeclaration):
                for var in decl.sequence:
                    class_properties.add(var.name)

    for member in class_declaration.body.members:
        if isinstance(member, node.FunctionDeclaration):
            function_name = member.name
            body = str(member.body) if member.body else ""

            # Skip constructor (same name as class)
            if function_name == class_declaration.name:
                continue

            # Strip whitespace and remove line breaks
            clean_body = body.replace("\n", "").strip()

            # Possible accessor/mutator detection
            is_accessor = (
                function_name.startswith("get") or function_name.startswith("is")
            ) and any(prop in clean_body for prop in class_properties)

            is_mutator = (
                function_name.startswith("set") and any(f"{prop} =" in clean_body for prop in class_properties)
            )

            if not (is_accessor or is_mutator):
                nomnamm_count += 1

    return nomnamm_count

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

def count_nim_type(class_declaration):
    """
    Menghitung jumlah metode yang diwariskan dari kelas induk (NIM_type).
    """
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        return 0
    
    # In Kotlin, inherited methods come from:
    # 1. Superclass (Any class by default)
    # 2. Interfaces
    # This is a simplified approach that counts overridden methods
    
    nim_count = 0
    
    for member in class_declaration.body.members:
        if isinstance(member, node.FunctionDeclaration):
            # Check if the method has 'override' modifier
            if hasattr(member, 'modifiers') and member.modifiers:
                for modifier in member.modifiers:
                    if str(modifier).strip() == 'override':
                        nim_count += 1
                        break
    
    return nim_count

def extracted_method(file_path):
    """Ekstrak informasi metode dari file Kotlin dengan metrik lengkap (refined FANOUT_method)."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        parser = Parser(code)
        result = parser.parse()
        package_name = result.package.name if result.package else "Unknown"

        if not result.declarations:
            return [{
                "Package": package_name, 
                "Class": "Unknown", 
                "Method": "None", 
                "LOC": 0, 
                "Max Nesting": 0, 
                "CC": 0, 
                "WOC": 0, 
                "NOMNAMM_type": 0, 
                "NOA_type": 0,
                "NIM_type": 0,
                "Error": "No class declaration found"
            }]
        
        class_declaration = result.declarations[0]
        class_name = class_declaration.name
        
        if class_declaration.body is None:
            return [{
                "Package": package_name, 
                "Class": class_name, 
                "Method": "None", 
                "LOC": 0, 
                "Max Nesting": 0, 
                "CC": 0, 
                "WOC": 0, 
                "NOMNAMM_type": 0, 
                "NOA_type": 0,
                "NIM_type": 0,
                "Error": "Class has no body"
            }]
        
        datas = []
        method_function = {}

        nomnamm_total = count_nomnamm_type(class_declaration)
        noa_total = count_noa_type(class_declaration)
        nim_total = count_nim_type(class_declaration)

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
                "NOMNAMM_type": nomnamm_total,
                "NOA_type": noa_total,
                "NIM_type": nim_total,
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
            "NOMNAMM_type": nomnamm_total,
            "NOA_type": noa_total,
            "NIM_type": nim_total,
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
            "NOMNAMM_type": 0,
            "NOA_type": 0,
            "NIM_type": 0,
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