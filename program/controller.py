import os
import tempfile
import patoolib
import pandas as pd
from kopyt import Parser, node  # Gunakan `kopyt` sebagai parser AST Kotlin

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

def count_atfd_type(class_declaration):
    foreign_accesses = set()

    # Collect current class field names
    current_fields = {
        member.declaration.name
        for member in class_declaration.body.members
        if isinstance(member, node.PropertyDeclaration)
    }

    def collect_foreign_accesses(expr):
        if isinstance(expr, node.PostfixUnaryExpression):
            if isinstance(expr.expression, node.Identifier):
                root_name = expr.expression.value
                if root_name not in current_fields and root_name != "this":
                    foreign_accesses.add(root_name)

            for suffix in expr.suffixes:
                if isinstance(suffix, node.NavigationSuffix):
                    if isinstance(expr.expression, node.Identifier):
                        base = expr.expression.value
                        if base not in current_fields and base != "this":
                            foreign_accesses.add(base)

        elif isinstance(expr, node.Assignment):
            collect_foreign_accesses(expr.value)

        elif isinstance(expr, node.Identifier):
            if expr.value not in current_fields and expr.value != "this":
                foreign_accesses.add(expr.value)

        elif hasattr(expr, "__dict__"):
            for val in vars(expr).values():
                if isinstance(val, node.Node):
                    collect_foreign_accesses(val)
                elif isinstance(val, (list, tuple)):
                    for item in val:
                        if isinstance(item, node.Node):
                            collect_foreign_accesses(item)

    # Visit all methods in the class
    for member in class_declaration.body.members:
        if isinstance(member, node.FunctionDeclaration):
            body = member.body
            if isinstance(body, node.Block):
                for stmt in body.sequence:
                    collect_foreign_accesses(stmt.statement)

    return len(foreign_accesses)

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

def count_atld_method(method_node, class_fields):
    attributes_accessed = set()
    local_variables = set()

    # Step 1: parameters as locals
    if hasattr(method_node, 'parameters'):
        for param in method_node.parameters:
            if hasattr(param, 'name'):
                local_variables.add(param.name)

    # Step 2: fallback to body text scan
    body_text = str(method_node.body) if method_node.body else ""

    # Detect class attributes used
    for field in class_fields:
        if field in body_text:
            attributes_accessed.add(field)

    # Detect locals by looking for `val` / `var` declarations
    for line in body_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("val ") or stripped.startswith("var "):
            parts = stripped.split()
            if len(parts) >= 2:
                var_name = parts[1].split("=")[0].strip()
                if var_name.isidentifier():
                    local_variables.add(var_name)

    # Final calculation
    local_count = len(local_variables)
    attr_count = len(attributes_accessed)

    return round(attr_count / local_count, 2) if local_count > 0 else float(attr_count)




def extracted_method(file_path):
    """Ekstrak informasi metode dari file Kotlin dengan semua metrik termasuk ATLD_method."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        parser = Parser(code)
        result = parser.parse()
        # print("Parsed members:", class_declaration.body.members)

        package_name = result.package.name if result.package else "Unknown"

        if not result.declarations:
            return [{
                "Package": package_name, 
                "Class": "Unknown", 
                "Method": "None", 
                "LOC": 0, 
                "NOMNAMM_type": 0, 
                "NOA_type": 0,
                "NIM_type": 0,
                "ATFD_type": 0,
                "FANOUT_method": 0,
                "ATLD_method": 0,
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
                "NOMNAMM_type": 0, 
                "NOA_type": 0,
                "NIM_type": 0,
                "ATFD_type": 0,
                "FANOUT_method": 0,
                "ATLD_method": 0,
                "Error": "Class has no body"
            }]
        
        datas = []
        method_function = {}

        nomnamm_total = count_nomnamm_type(class_declaration)
        noa_total = count_noa_type(class_declaration)
        nim_total = count_nim_type(class_declaration)
        atfd_total = count_atfd_type(class_declaration)

        # Collect class-level attribute names
        class_fields = set()
        for member in class_declaration.body.members:
            if isinstance(member, node.PropertyDeclaration):
                decl = member.declaration
                if isinstance(decl, node.VariableDeclaration):
                    class_fields.add(decl.name)
                elif isinstance(decl, node.MultiVariableDeclaration):
                    for var in decl.sequence:
                        class_fields.add(var.name)

        for member in class_declaration.body.members:
            if isinstance(member, node.FunctionDeclaration):
                try:
                    function_name = member.name
                    body_str = str(member.body) if member.body else ""
                    
                    loc_count = body_str.count('\n') + 1 if body_str else 0
                    fanout_value = count_fanout_method(body_str) if body_str else 0
                    atld_value = count_atld_method(member, class_fields)

                    method_function[function_name] = (loc_count, fanout_value, atld_value)
                except Exception as e:
                    print(f"Error processing method {getattr(member, 'name', 'unknown')}: {str(e)}")
                    continue

        for function_name, (loc_count, fanout_value, atld_value) in method_function.items():
            datas.append({
                "Package": package_name,
                "Class": class_name,
                "Method": function_name,
                "LOC": loc_count,
                "NOMNAMM_type": nomnamm_total,
                "NOA_type": noa_total,
                "NIM_type": nim_total,
                "ATFD_type": atfd_total,
                "FANOUT_method": fanout_value,
                "ATLD_method": atld_value,
                "Error": ""
            })

        return datas if datas else [{
            "Package": package_name,
            "Class": class_name,
            "Method": "None",
            "LOC": 0,
            "NOMNAMM_type": nomnamm_total,
            "NOA_type": noa_total,
            "NIM_type": nim_total,
            "ATFD_type": atfd_total,
            "FANOUT_method": 0,
            "ATLD_method": 0,
            "Error": "No functions found" if class_declaration.body.members else "Class has no members"
        }]
    
    except Exception as e:
        return [{
            "Package": "Error",
            "Class": "Error",
            "Method": "Error",
            "LOC": 0,
            "NOMNAMM_type": 0,
            "NOA_type": 0,
            "NIM_type": 0,
            "ATFD_type": 0,
            "FANOUT_method": 0,
            "ATLD_method": 0,
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
