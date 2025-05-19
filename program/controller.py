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


def count_fanout_type(class_declaration: node.ClassDeclaration) -> int:
    """
    Count the number of unique external classes used by this class (FANOUT_type).
    """
    if not class_declaration or class_declaration.body is None:
        return 0

    current_class_name = class_declaration.name
    referenced_classes = set()

    # Helper to extract type names recursively
    def extract_type_names(type_node):
        names = set()
        if type_node is None:
            return names
        try:
            type_str = str(type_node)
            raw = type_str.replace("<", " ").replace(">", " ").replace(",", " ")
            for part in raw.split():
                if part[0].isupper() and part != current_class_name:
                    names.add(part)
        except Exception:
            pass
        return names

    # Check supertypes (inheritance or interface)
    if hasattr(class_declaration, 'supertypes'):
        for supertype in class_declaration.supertypes:
            referenced_classes |= extract_type_names(supertype)

    # Check type parameters constraints
    if hasattr(class_declaration, 'constraints'):
        for constraint in class_declaration.constraints:
            referenced_classes |= extract_type_names(constraint.type)

    # Check inside body
    for member in class_declaration.body.members:
        if isinstance(member, node.PropertyDeclaration):
            decl = getattr(member, 'declaration', None)
            if isinstance(decl, node.VariableDeclaration) and decl.type:
                referenced_classes |= extract_type_names(decl.type)
            elif isinstance(decl, node.MultiVariableDeclaration):
                for var in decl.sequence:
                    if var.type:
                        referenced_classes |= extract_type_names(var.type)

            # Delegate
            if member.delegate:
                referenced_classes |= extract_type_names(member.delegate.value)

        elif isinstance(member, node.FunctionDeclaration):
            if member.type:
                referenced_classes |= extract_type_names(member.type)  # return type
            for param in getattr(member, 'parameters', []):
                if param.type:
                    referenced_classes |= extract_type_names(param.type)

        elif isinstance(member, node.SecondaryConstructor):
            for param in member.parameters:
                if param.type:
                    referenced_classes |= extract_type_names(param.type)

        elif isinstance(member, node.CompanionObject) and member.body:
            for inner_member in member.body.members:
                if isinstance(inner_member, node.PropertyDeclaration):
                    decl = getattr(inner_member, 'declaration', None)
                    if isinstance(decl, node.VariableDeclaration) and decl.type:
                        referenced_classes |= extract_type_names(decl.type)
                    elif isinstance(decl, node.MultiVariableDeclaration):
                        for var in decl.sequence:
                            if var.type:
                                referenced_classes |= extract_type_names(var.type)

    # Remove Kotlin built-ins
    kotlin_builtins = {
        'String', 'Int', 'Double', 'Float', 'Boolean', 'Array', 'List', 'Set',
        'Map', 'Collection', 'Pair', 'Triple', 'Unit', 'Any', 'Nothing', 'Exception',
        'Throwable', 'Char', 'Long', 'Short', 'Byte'
    }

    return len(referenced_classes - kotlin_builtins)

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

def count_fanout_method(method_body: str, class_methods=None) -> int:
    """
    Refined FANOUT_method metric:
    Count unique external class or method calls from a method body.

    Args:
        method_body (str): Method code as string.
        class_methods (set): Optional, names of own class methods to exclude from count.

    Returns:
        int: Number of unique external class or method calls.
    """
    if not method_body:
        return 0

    external_calls = set()
    class_methods = class_methods or set()

    lines = method_body.split('\n')

    for line in lines:
        line = line.strip()

        if not line or line.startswith('//') or line.startswith('/*'):
            continue

        # Case 1: object.method() or safe-call obj?.method()
        if '.' in line and '(' in line:
            segments = line.replace('?.', '.').split('.')
            for i in range(len(segments) - 1):
                receiver = segments[i].strip().split(' ')[-1]
                method_part = segments[i + 1].split('(')[0].strip()

                if receiver not in ('this', 'super', ''):
                    external_calls.add(f"{receiver}.{method_part}")

        # Case 2: direct method calls (no dot)
        elif '(' in line:
            candidate = line.split('(')[0].strip()
            if candidate and candidate not in class_methods:
                external_calls.add(candidate)

    return len(external_calls)

def count_cfnamm_method(class_declaration):
    """
    Refined CFNAMM_method using Kopyt nodes (no regex).
    """
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        return 0

    non_accessor_mutator_methods = {}

    # Step 1: Identify all non-accessor/mutator methods
    for member in class_declaration.body.members:
        if isinstance(member, node.FunctionDeclaration):
            name = member.name

            # Skip constructor
            if name == class_declaration.name:
                continue

            # Skip getter/setter style
            if name.startswith("get") or name.startswith("set") or name.startswith("is"):
                continue

            body_str = str(member.body) if member.body else ""
            non_accessor_mutator_methods[name] = body_str

    total = len(non_accessor_mutator_methods)
    if total == 0:
        return 0

    # Step 2: Check for coupling (calls to other non-acc/mut methods)
    coupled = set()

    method_names = set(non_accessor_mutator_methods.keys())
    for method_name, body in non_accessor_mutator_methods.items():
        for target in method_names:
            if method_name == target:
                continue
            # Manual string-based check without regex
            index = 0
            while True:
                index = body.find(target, index)
                if index == -1:
                    break
                after = body[index + len(target):]
                if after.lstrip().startswith("("):
                    coupled.add(method_name)
                    break
                index += len(target)

    return len(coupled) / total

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

        atfd_total = count_atfd_type(class_declaration)
        fanout_total = count_fanout_type(class_declaration)
        nomnamm_total = count_nomnamm_type(class_declaration)
        noa_total = count_noa_type(class_declaration)
        nim_total = count_nim_type(class_declaration)
        dit_total = count_dit_type(class_declaration)
        cfnamm_total = count_cfnamm_method(class_declaration)

        # ✅ Collect own method names to exclude self-calls in FANOUT_method
        own_methods = {
            m.name for m in class_declaration.body.members
            if isinstance(m, node.FunctionDeclaration)
        }

        fanout_method_values = {}

        for member in class_declaration.body.members:
            if isinstance(member, node.FunctionDeclaration):
                try:
                    function_name = member.name
                    body_str = str(member.body) if member.body else ""
                    
                    loc_count = body_str.count('\n') + 1 if body_str else 0
                    maxnesting = manual_max_nesting(body_str) if body_str else 0
                    cc_value = count_cc_manual(body_str) if body_str else 0
                    fanout_method = count_fanout_method(body_str, class_methods=own_methods) if body_str else 0
                    
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
