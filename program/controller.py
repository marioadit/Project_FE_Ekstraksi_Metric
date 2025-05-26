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

def count_cfnamm_method(class_declaration):
    """
    Menghitung CFNAMM_method per method: 
    berapa banyak metode non-AM lain yang dipanggil oleh masing-masing method.
    """
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        return {}

    methods = {}
    class_properties = set()

    # 1. Kumpulkan semua properti
    for member in class_declaration.body.members:
        if isinstance(member, node.PropertyDeclaration):
            decl = member.declaration
            if isinstance(decl, node.VariableDeclaration):
                class_properties.add(decl.name)
            elif isinstance(decl, node.MultiVariableDeclaration):
                for var in decl.sequence:
                    class_properties.add(var.name)

    # 2. Ambil method non-AM
    for member in class_declaration.body.members:
        if isinstance(member, node.FunctionDeclaration):
            function_name = member.name
            if function_name == class_declaration.name:
                continue

            body_str = str(member.body) if member.body else ""
            clean_body = body_str.replace('\n', '').strip()

            is_accessor = (
                function_name.startswith("get") or function_name.startswith("is")
            ) and any(prop in clean_body for prop in class_properties)

            is_mutator = (
                function_name.startswith("set") and any(f"{prop} =" in clean_body for prop in class_properties)
            )

            if not (is_accessor or is_mutator):
                methods[function_name] = body_str

    if not methods:
        return {}

    method_names = set(methods.keys())
    cfnamm_per_method = {}

    # 3. Untuk tiap method, hitung coupling terhadap method lain
    for method_name, body_str in methods.items():
        calls = 0
        for other in method_names:
            if other != method_name and f"{other}(" in body_str:
                calls += 1
        max_possible = len(method_names) - 1
        ratio = round(calls / max_possible, 2) if max_possible > 0 else 0.0
        cfnamm_per_method[method_name] = ratio

    return cfnamm_per_method

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

def count_fanout_type(class_declaration):
    """
    FANOUT_type — inspects function bodies, property types/values, parameter types, return types, and supertypes.
    """
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        print("⛔️ No class body.")
        return 0

    external_types = set()

    def collect_types(n, depth=0):
        prefix = "  " * depth

        if isinstance(n, node.TypeReference):
            print(f"{prefix}🔍 TypeReference → {n}")
            if isinstance(n.subtype, node.UserType):
                for segment in n.subtype.sequence:
                    if isinstance(segment, node.SimpleUserType):
                        name = segment.name
                        # print(f"{prefix}  📎 Found type: {name}")
                        if name and name[0].isupper():
                            external_types.add(name)

        elif isinstance(n, node.ConstructorInvocation):
            print(f"{prefix}🔧 ConstructorInvocation → {n}")
            if isinstance(n.invoker, node.UserType):
                for segment in n.invoker.sequence:
                    if isinstance(segment, node.SimpleUserType):
                        name = segment.name
                        # print(f"{prefix}  🏗 Instantiates class: {name}")
                        if name and name[0].isupper():
                            external_types.add(name)

        elif isinstance(n, node.UserType):
            for segment in n.sequence:
                if isinstance(segment, node.SimpleUserType):
                    name = segment.name
                    # print(f"{prefix}📎 UserType segment: {name}")
                    if name and name[0].isupper():
                        external_types.add(name)

        # Deep recursive search
        if hasattr(n, '__dict__'):
            for val in vars(n).values():
                if isinstance(val, node.Node):
                    collect_types(val, depth + 1)
                elif isinstance(val, (list, tuple)):
                    for item in val:
                        if isinstance(item, node.Node):
                            collect_types(item, depth + 1)

    # Visit supertypes (inheritance/interfaces)
    if hasattr(class_declaration, 'supertypes') and class_declaration.supertypes:
        for supertype in class_declaration.supertypes:
            collect_types(supertype)

    # Visit class parameters (constructor properties)
    if hasattr(class_declaration, 'constructor') and class_declaration.constructor:
        for param in getattr(class_declaration.constructor.parameters, 'sequence', []):
            collect_types(param.type)

    for member in class_declaration.body.members:
        # print(f"Member: {type(member).__name__}")

        # Property types
        if isinstance(member, node.PropertyDeclaration):
            decl = getattr(member, 'declaration', None)
            if isinstance(decl, node.VariableDeclaration):
                if decl.type:
                    collect_types(decl.type)
            elif isinstance(decl, node.MultiVariableDeclaration):
                for var in decl.sequence:
                    if var.type:
                        collect_types(var.type)
            if member.value:
                collect_types(member.value)

        # Function parameter types and return type
        elif isinstance(member, node.FunctionDeclaration):
            if hasattr(member, 'parameters'):
                for param in getattr(member.parameters, 'sequence', []):
                    if hasattr(param, 'parameter') and hasattr(param.parameter, 'type') and param.parameter.type:
                        collect_types(param.parameter.type)
            if hasattr(member, 'type') and member.type:
                collect_types(member.type)
            if member.body:
                collect_types(member.body)

        else:
            collect_types(member)

    # print(f"✅ Total unique external types found: {len(external_types)}")
    # print(f"🧾 Types: {external_types}")
    return len(external_types)

def count_fanout_type_manual(code: str) -> int:
    """
    FANOUT_type_manual — without regex.
    Scans for:
    - Type annotations (val x: Type)
    - Constructor calls (Type(...))
    """
    types = set()

    for line in code.splitlines():
        line = line.strip()

        if not line or line.startswith('//') or line.startswith('/*'):
            continue

        # ---- Type annotation detection ----
        if ':' in line:
            colon_index = line.index(':')
            after_colon = line[colon_index + 1:].lstrip()

            end = 0
            while end < len(after_colon) and after_colon[end] not in ' =({,);':
                end += 1
            candidate = after_colon[:end]

            if candidate and candidate[0].isupper():
                types.add(candidate)

        # ---- Constructor call detection ----
        i = 0
        while i < len(line):
            if line[i].isalpha() and line[i].isupper():
                start = i
                while i < len(line) and (line[i].isalnum() or line[i] == '_'):
                    i += 1
                name = line[start:i]

                # Check for immediate open paren after optional spaces
                j = i
                while j < len(line) and line[j] == ' ':
                    j += 1
                if j < len(line) and line[j] == '(':
                    types.add(name)
            else:
                i += 1

    return len(types)



def extracted_method(file_path):
    """Ekstrak informasi metode dari file Kotlin dengan semua metrik termasuk ATLD_method dan FANOUT_type_manual."""
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
                "NOMNAMM_type": 0, 
                "NOA_type": 0,
                "NIM_type": 0,
                "ATFD_type": 0,
                "FANOUT_type": 0,
                "FANOUT_type_manual": 0,  # Removed regex version
                "FANOUT_method": 0,
                "ATLD_method": 0,
                "CFNAMM_method": 0.0,
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
                "FANOUT_type": 0,
                "FANOUT_type_manual": 0,  # Removed regex version
                "FANOUT_method": 0,
                "ATLD_method": 0,
                "CFNAMM_method": 0.0,
                "Error": "Class has no body"
            }]
        
        datas = []
        method_function = {}

        nomnamm_total = count_nomnamm_type(class_declaration)
        noa_total = count_noa_type(class_declaration)
        nim_total = count_nim_type(class_declaration)
        atfd_total = count_atfd_type(class_declaration)
        fanout_total = count_fanout_type(class_declaration)
        fanout_manual_total = count_fanout_type_manual(code)  # Only manual version
        cfnamm_total = count_cfnamm_method(class_declaration)

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
            cfnamm_value = cfnamm_total.get(function_name, 0.0)
            if isinstance(cfnamm_value, dict):
                cfnamm_value = 0.0

            datas.append({
                "Package": package_name,
                "Class": class_name,
                "Method": function_name,
                "LOC": loc_count,
                "NOMNAMM_type": nomnamm_total,
                "NOA_type": noa_total,
                "NIM_type": nim_total,
                "ATFD_type": atfd_total,
                "FANOUT_type": fanout_total,
                "FANOUT_type_manual": fanout_manual_total,  # Only manual version
                "FANOUT_method": fanout_value,
                "ATLD_method": atld_value,
                "CFNAMM_method": float(cfnamm_value),
                "Error": ""
            })

        for row in datas:
            for k, v in row.items():
                if isinstance(v, dict):
                    row[k] = str(v)

        return datas if datas else [{
            "Package": package_name,
            "Class": class_name,
            "Method": "None",
            "LOC": 0,
            "NOMNAMM_type": nomnamm_total,
            "NOA_type": noa_total,
            "NIM_type": nim_total,
            "ATFD_type": atfd_total,
            "FANOUT_type": fanout_total,
            "FANOUT_type_manual": fanout_manual_total,  # Only manual version
            "FANOUT_method": 0,
            "ATLD_method": 0,
            "CFNAMM_method": 0.0,
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
            "FANOUT_type": 0,
            "FANOUT_type_manual": 0,  # Only manual version
            "FANOUT_method": 0,
            "ATLD_method": 0,
            "CFNAMM_method": 0.0,
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
