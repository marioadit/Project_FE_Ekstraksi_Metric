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
    Improved ATFD_type (Access to Foreign Data) for a Kotlin class.
    """
    atfd = 0
    try:
        if class_declaration.body is None:
            return 0
        
        class_name = class_declaration.name
        for member in class_declaration.body.members:
            if isinstance(member, node.FunctionDeclaration) and member.body:
                body_str = str(member.body)
                if not body_str:
                    continue

                # Step 1: Collect parameters
                param_names = set()
                if hasattr(member, 'parameters'):
                    for param in member.parameters:
                        if hasattr(param, 'name'):
                            param_names.add(param.name)

                # Step 2: Find potential foreign accesses
                lines = body_str.split('\n')
                for line in lines:
                    stripped = line.strip()
                    if not stripped or '.' not in stripped:
                        continue

                    parts = stripped.split('.')
                    for i in range(len(parts) - 1):
                        receiver = parts[i].strip()
                        accessed = parts[i + 1].strip()

                        # Filter out method calls (like obj.method())
                        if accessed.endswith('()') or '(' in accessed:
                            continue

                        # Valid receiver: not 'this', 'super', class name, or parameter
                        if (receiver and receiver[0].islower() and 
                            receiver not in ('this', 'super') and
                            receiver != class_name and
                            receiver not in param_names and
                            not any(c in receiver for c in '(){}[]')):

                            atfd += 1
    except Exception as e:
        print(f"Error in count_atfd_type: {str(e)}")
        return 0
    
    return atfd


def count_fanout_type(class_code):
    """Menghitung jumlah kelas lain yang digunakan oleh kelas ini (FANOUT_type) menggunakan AST."""
    try:
        parser = Parser(class_code)
        ast = parser.parse()
        
        referenced_classes = set()
        current_class_name = None
        
        # Find the current class name
        if ast.declarations:
            for decl in ast.declarations:
                if isinstance(decl, node.ClassDeclaration):
                    current_class_name = decl.name
                    break
        
        # Process imports to find referenced classes
        if hasattr(ast, 'imports') and ast.imports:
            for imp in ast.imports:
                import_str = str(imp)
                components = import_str.split('.')
                for comp in components:
                    if comp and comp[0].isupper() and comp != current_class_name:
                        referenced_classes.add(comp)
        
        # Process class body to find referenced classes
        if ast.declarations:
            for decl in ast.declarations:
                if isinstance(decl, node.ClassDeclaration) and decl.body:
                    # Check property types
                    for member in decl.body.members:
                        # Safely check PropertyDeclaration type
                        if isinstance(member, node.PropertyDeclaration):
                            if hasattr(member, 'type') and member.type:
                                type_str = str(member.type)
                                for name in [t.strip() for t in type_str.replace("<", " ").replace(">", " ").split()]:
                                    if name and name[0].isupper() and name != current_class_name:
                                        referenced_classes.add(name)
                        
                        # Check function parameters and return types
                        if isinstance(member, node.FunctionDeclaration):
                            if hasattr(member, 'parameters') and member.parameters:
                                for param in member.parameters:
                                    if hasattr(param, 'type') and param.type:
                                        type_str = str(param.type)
                                        for name in [t.strip() for t in type_str.replace("<", " ").replace(">", " ").split()]:
                                            if name and name[0].isupper() and name != current_class_name:
                                                referenced_classes.add(name)
                            
                            if hasattr(member, 'returnType') and member.returnType:
                                type_str = str(member.returnType)
                                for name in [t.strip() for t in type_str.replace("<", " ").replace(">", " ").split()]:
                                    if name and name[0].isupper() and name != current_class_name:
                                        referenced_classes.add(name)
        
        # Filter out common Kotlin types
        kotlin_types = {'String', 'Int', 'Double', 'Float', 'Boolean', 'Array',
                      'List', 'Set', 'Map', 'Collection', 'Pair', 'Triple', 'Unit', 
                      'Any', 'Nothing', 'Throwable', 'Exception'}
        
        referenced_classes = {cls for cls in referenced_classes if cls not in kotlin_types}
        
        return len(referenced_classes)
    
    except Exception as e:
        print(f"Error in count_fanout: {str(e)}")
        return 0

def count_nomnamm_type(class_declaration):
    """Menghitung jumlah metode yang bukan accessor atau mutator (NOMNAMM_type)."""
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        return 0
    
    nomnamm_count = 0
    
    for member in class_declaration.body.members:
        if isinstance(member, node.FunctionDeclaration):
            function_name = member.name
            
            # Skip constructor
            if function_name == class_declaration.name:
                continue
                
            # Check if it's an accessor (getter) or mutator (setter)
            is_accessor_or_mutator = False
            
            # Accessor typically starts with 'get' or has no prefix but returns a class property
            if function_name.startswith('get') or function_name.startswith('is'):
                is_accessor_or_mutator = True
            
            # Mutator typically starts with 'set' and changes a class property
            elif function_name.startswith('set'):
                is_accessor_or_mutator = True
            
            # If not identified as accessor/mutator, count it
            if not is_accessor_or_mutator:
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

def count_dit_type(class_declaration):
    """
    Menghitung Depth of Inheritance Tree (DIT_type) untuk sebuah kelas Kotlin.
    DIT_type adalah panjang jalur warisan dari kelas saat ini ke kelas root.
    """
    # Every Kotlin class implicitly extends Any, so minimum DIT is 1
    dit = 1
    
    # Check if the class explicitly extends another class
    if hasattr(class_declaration, 'parents') and class_declaration.parents:
        for parent in class_declaration.parents:
            # We count only class inheritance (not interface implementation)
            parent_str = str(parent).strip()
            if ':' in parent_str:  # Format typically is "class A : B()"
                parent_type = parent_str.split(':')[1].strip().split('(')[0].strip()
                # Ignore Any and interfaces (simplified heuristic)
                if parent_type != 'Any' and not parent_type.endswith('able'):
                    dit += 1
    
    return dit

def count_fanout_method(method_body):
    """
    Menghitung FANOUT_method - jumlah kelas atau fungsi berbeda yang dipanggil dalam suatu metode.
    
    Args:
        method_body (str): Kode metode yang akan dianalisis
    
    Returns:
        int: Jumlah panggilan unik ke metode/kelas eksternal
    """
    if not method_body:
        return 0
        
    # Set untuk menyimpan panggilan unik
    external_calls = set()
    
    # Memisahkan kode menjadi baris-baris
    lines = method_body.split('\n')
    
    for line in lines:
        stripped = line.strip()
        
        # Lewati baris kosong dan komentar
        if not stripped or stripped.startswith('//') or stripped.startswith('/*'):
            continue
            
        # Deteksi panggilan metode
        # 1. Panggilan dengan format: object.method()
        if '.' in stripped and '(' in stripped:
            parts = stripped.split('.')
            for i in range(len(parts) - 1):
                if '(' in parts[i+1]:
                    receiver = parts[i].strip().split(' ')[-1]  # ambil objek yang memanggil metode
                    method = parts[i+1].split('(')[0].strip()   # ambil nama metode yang dipanggil
                    
                    # Tidak menghitung this/super
                    if receiver not in ('this', 'super'):
                        # Tambah ke set panggilan eksternal
                        external_calls.add(f"{receiver}.{method}")
        
        # 2. Panggilan langsung: method()
        elif '(' in stripped and not stripped.startswith(('if', 'for', 'while', 'when', 'switch')):
            method_name = stripped.split('(')[0].strip()
            if method_name and not any(keyword in method_name for keyword in ('if', 'for', 'while', 'when')):
                # Untuk panggilan langsung, kita hanya tambahkan nama metode
                external_calls.add(method_name)
    
    return len(external_calls)

def count_cfnamm_method(class_declaration):
    """
    Menghitung CFNAMM_method (Coupling Factor of Non-Accessor and Mutator Methods) untuk sebuah kelas.
    CFNAMM_method = (Number of Non-Accessor/Mutator Methods Coupled) / (Total Non-Accessor/Mutator Methods)
    """
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        return 0
    
    # Identifikasi semua metode non-accessor/non-mutator
    non_acc_mut_methods = []
    coupled_methods = set()
    
    for member in class_declaration.body.members:
        if isinstance(member, node.FunctionDeclaration):
            function_name = member.name
            
            # Skip constructor
            if function_name == class_declaration.name:
                continue
                
            # Check if it's an accessor (getter) or mutator (setter)
            is_accessor_or_mutator = False
            
            # Accessor typically starts with 'get' or has no prefix but returns a class property
            if function_name.startswith('get') or function_name.startswith('is'):
                is_accessor_or_mutator = True
            
            # Mutator typically starts with 'set' and changes a class property
            elif function_name.startswith('set'):
                is_accessor_or_mutator = True
            
            # Store non-accessor/mutator methods for analysis
            if not is_accessor_or_mutator:
                body_str = str(member.body) if member.body else ""
                non_acc_mut_methods.append((function_name, body_str))
    
    # If there are no non-accessor/mutator methods, return 0
    total_non_acc_mut = len(non_acc_mut_methods)
    if total_non_acc_mut == 0:
        return 0
    
    # Check coupling between methods
    for method_name, body_str in non_acc_mut_methods:
        # A method is coupled if it calls another method in the class
        for other_method_name, _ in non_acc_mut_methods:
            if method_name != other_method_name and other_method_name in body_str:
                coupled_methods.add(method_name)
                break
    
    # Calculate CFNAMM_method
    coupled_count = len(coupled_methods)
    return coupled_count / total_non_acc_mut if total_non_acc_mut > 0 else 0

def extracted_method(file_path):
    """Ekstrak informasi metode dari file Kotlin, termasuk ATFD_type, FANOUT_type, NOMNAMM_type, NOA_type, NIM_type, DIT_type, dan FANOUT_method."""
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
                "ATFD_type": 0, 
                "FANOUT_type": 0, 
                "NOMNAMM_type": 0, 
                "NOA_type": 0,
                "NIM_type": 0,
                "DIT_type": 0,
                "FANOUT_method": 0,
                "CFNAMM_method": 0,
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
                "ATFD_type": 0, 
                "FANOUT_type": 0, 
                "NOMNAMM_type": 0, 
                "NOA_type": 0,
                "NIM_type": 0,
                "DIT_type": 0,
                "FANOUT_method": 0,
                "CFNAMM_method": 0,
                "Error": "Class has no body"
            }]
        
        datas = []
        method_function = {}
        
        # Hitung metrik tingkat kelas
        atfd_total = count_atfd_type(class_declaration)
        fanout_total = count_fanout_type(code)
        nomnamm_total = count_nomnamm_type(class_declaration)
        noa_total = count_noa_type(class_declaration)
        nim_total = count_nim_type(class_declaration)
        dit_total = count_dit_type(class_declaration)
        cfnamm_total = count_cfnamm_method(class_declaration)
        
        # Dictionary untuk menyimpan nilai FANOUT_method
        fanout_method_values = {}
        
        for member in class_declaration.body.members:
            if isinstance(member, node.FunctionDeclaration):
                try:
                    function_name = member.name
                    body_str = str(member.body) if member.body else ""
                    
                    loc_count = body_str.count('\n') + 1 if body_str else 0
                    maxnesting = manual_max_nesting(body_str) if body_str else 0
                    cc_value = count_cc_manual(body_str) if body_str else 0
                    fanout_method = count_fanout_method(body_str) if body_str else 0
                    
                    method_function[function_name] = (cc_value, loc_count, maxnesting)
                    fanout_method_values[function_name] = fanout_method
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
                "ATFD_type": atfd_total,
                "FANOUT_type": fanout_total,
                "NOMNAMM_type": nomnamm_total,
                "NOA_type": noa_total,
                "NIM_type": nim_total,
                "DIT_type": dit_total,
                "FANOUT_method": fanout_method_values.get(function_name, 0),
                "CFNAMM_method": cfnamm_total,
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
            "NOMNAMM_type": nomnamm_total,
            "NOA_type": noa_total,
            "NIM_type": nim_total,
            "DIT_type": dit_total,
            "FANOUT_method": 0,
            "CFNAMM_method": cfnamm_total,
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
            "NOMNAMM_type": 0,
            "NOA_type": 0,
            "NIM_type": 0,
            "DIT_type": 0,
            "FANOUT_method": 0,
            "CFNAMM_method": 0,
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
