import os
import tempfile
import patoolib
import pandas as pd
from kopyt import Parser, node
from typing import Set # Import Set untuk type hinting

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

# Fungsi DIT_type yang sudah diperbaiki untuk memanfaatkan kopyt
def count_dit_type(class_declaration) -> int:
    """
    Menghitung Depth of Inheritance Tree (DIT_type) untuk sebuah kelas
    menggunakan node kopyt.

    Interpretasi untuk parser satu file:
    - DIT = 0 jika kelas tidak memiliki supertype eksplisit.
    - DIT = 1 jika kelas memiliki setidaknya satu supertype eksplisit
      (baik kelas maupun antarmuka).
    """
    # Periksa apakah class_declaration memiliki atribut supertypes
    if hasattr(class_declaration, 'supertypes') and class_declaration.supertypes:
        # supertypes adalah Sequence[AnnotatedDelegationSpecifier]
        # Jika sequence ini tidak kosong, berarti ada pewarisan eksplisit.
        return 1
    
    # Untuk kasus di mana kelas mungkin tidak memiliki 'body'
    # tetapi memiliki 'supertypes' (misalnya, interface)
    # ClassDeclaration juga memiliki atribut supertypes.
    # Contoh: class MyClass : SomeParent
    if isinstance(class_declaration, node.ClassDeclaration) and class_declaration.supertypes:
        return 1

    # Jika tidak ada supertype eksplisit yang ditemukan, DIT adalah 0.
    # Ini berarti kelas hanya mewarisi dari kotlin.Any secara implisit.
    return 0


def extracted_method(file_path):
    """Ekstrak informasi metode dari file Kotlin dengan semua metrik termasuk ATLD_method."""
    results_for_file = [] # Mengumpulkan hasil untuk semua kelas/metode dalam file ini
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        parser = Parser(code)
        result = parser.parse()

        package_name = result.package.name if result.package else "Unknown"

        if not result.declarations:
            # Jika tidak ada deklarasi (kelas/object/interface), catat sebagai file tanpa kelas
            results_for_file.append({
                "Package": package_name, 
                "Class": "No Class", 
                "Method": "None", 
                "LOC": len(code.splitlines()), 
                "NOMNAMM_type": 0, 
                "NOA_type": 0,
                "NIM_type": 0,
                "ATFD_type": 0,
                "DIT_type": 0, # Default 0 jika tidak ada deklarasi kelas
                "FANOUT_method": 0,
                "ATLD_method": 0,
                "CFNAMM_method": 0.0,
                "Error": "No class declaration found in file"
            })
            return results_for_file # Langsung kembali

        # Iterasi melalui semua deklarasi tingkat atas (top-level declarations)
        for class_declaration in result.declarations:
            # Pastikan ini benar-benar deklarasi kelas/object/interface yang memiliki body
            if not isinstance(class_declaration, (node.ClassDeclaration, node.ObjectDeclaration, node.InterfaceDeclaration)):
                # Handle cases where top-level declaration is a function or property, not a class/object/interface
                # For this context, we usually care about metrics per class, so skip other top-level decls
                # You might consider logging or adding a specific entry for non-class top-level declarations if needed.
                continue 

            class_name = class_declaration.name
            
            # Hitung DIT_type menggunakan fungsi yang sudah diperbaiki dengan kopyt
            dit_total = count_dit_type(class_declaration)

            if class_declaration.body is None:
                results_for_file.append({
                    "Package": package_name, 
                    "Class": class_name, 
                    "Method": "None", 
                    "LOC": 0, # Atau LOC untuk kelas kosong?
                    "NOMNAMM_type": 0, 
                    "NOA_type": 0,
                    "NIM_type": 0,
                    "ATFD_type": 0,
                    "DIT_type": dit_total, # Tambahkan DIT_type
                    "FANOUT_method": 0,
                    "ATLD_method": 0,
                    "CFNAMM_method": 0.0,
                    "Error": "Class has no body or members"
                })
                continue # Lanjutkan ke deklarasi berikutnya

            # Hitung metrik tingkat kelas
            nomnamm_total = count_nomnamm_type(class_declaration)
            noa_total = count_noa_type(class_declaration)
            nim_total = count_nim_type(class_declaration)
            atfd_total = count_atfd_type(class_declaration)
            cfnamm_total = count_cfnamm_method(class_declaration)

            # Collect class-level attribute names for ATLD_method
            class_fields = set()
            for member in class_declaration.body.members:
                if isinstance(member, node.PropertyDeclaration):
                    decl = member.declaration
                    if isinstance(decl, node.VariableDeclaration):
                        class_fields.add(decl.name)
                    elif isinstance(decl, node.MultiVariableDeclaration):
                        for var in decl.sequence:
                            class_fields.add(var.name)

            # Memproses setiap fungsi dalam kelas
            method_found_in_class = False
            for member in class_declaration.body.members:
                if isinstance(member, node.FunctionDeclaration):
                    method_found_in_class = True
                    try:
                        function_name = member.name
                        body_str = str(member.body) if member.body else ""
                        
                        loc_count = body_str.count('\n') + 1 if body_str else 0
                        fanout_value = count_fanout_method(body_str) if body_str else 0
                        atld_value = count_atld_method(member, class_fields)

                        cfnamm_value = cfnamm_total.get(function_name, 0.0)
                        if isinstance(cfnamm_value, dict):
                            cfnamm_value = 0.0

                        results_for_file.append({
                            "Package": package_name,
                            "Class": class_name,
                            "Method": function_name,
                            "LOC": loc_count,
                            "NOMNAMM_type": nomnamm_total,
                            "NOA_type": noa_total,
                            "NIM_type": nim_total,
                            "ATFD_type": atfd_total,
                            "DIT_type": dit_total, # Tambahkan DIT_type per baris method
                            "FANOUT_method": fanout_value,
                            "ATLD_method": atld_value,
                            "CFNAMM_method": float(cfnamm_value),
                            "Error": ""
                        })
                    except Exception as e:
                        # Tangani error per method, bukan per file
                        results_for_file.append({
                            "Package": package_name,
                            "Class": class_name,
                            "Method": getattr(member, 'name', 'Error_Method'),
                            "LOC": 0,
                            "NOMNAMM_type": nomnamm_total,
                            "NOA_type": noa_total,
                            "NIM_type": nim_total,
                            "ATFD_type": atfd_total,
                            "DIT_type": dit_total, # Tambahkan DIT_type pada error method
                            "FANOUT_method": 0,
                            "ATLD_method": 0,
                            "CFNAMM_method": 0.0,
                            "Error": f"Error processing method: {str(e)}"
                        })
                        continue # Lanjutkan ke method berikutnya

            if not method_found_in_class:
                # Jika kelas tidak memiliki fungsi, tambahkan satu baris untuk kelas tersebut
                results_for_file.append({
                    "Package": package_name,
                    "Class": class_name,
                    "Method": "None",
                    "LOC": len(str(class_declaration.body).splitlines()) if class_declaration.body else 0,
                    "NOMNAMM_type": nomnamm_total,
                    "NOA_type": noa_total,
                    "NIM_type": nim_total,
                    "ATFD_type": atfd_total,
                    "DIT_type": dit_total, # Tambahkan DIT_type pada kelas tanpa fungsi
                    "FANOUT_method": 0,
                    "ATLD_method": 0,
                    "CFNAMM_method": 0.0,
                    "Error": "No functions found in class"
                })

    except Exception as e:
        # Ini adalah fallback jika parsing file itu sendiri gagal
        results_for_file.append({
            "Package": "Error",
            "Class": "Error", 
            "Method": "Error",
            "LOC": 0,
            "NOMNAMM_type": 0,
            "NOA_type": 0,
            "NIM_type": 0,
            "ATFD_type": 0,
            "DIT_type": 0, # Default 0 pada error fatal
            "FANOUT_method": 0,
            "ATLD_method": 0,
            "CFNAMM_method": 0.0,
            "Error": f"Fatal error parsing file: {str(e)}"
        })

    # Pastikan tidak ada dict yang tersisa dalam output akhir
    for row in results_for_file:
        for k, v in row.items():
            if isinstance(v, dict):
                row[k] = str(v) 

    return results_for_file

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
            # Jika ekstraksi arsip gagal atau tidak ada file Kotlin yang ditemukan
            return pd.DataFrame([{
                "Package": "Error",
                "Class": "Error",
                "Method": "Error",
                "LOC": 0,
                "NOMNAMM_type": 0,
                "NOA_type": 0,
                "NIM_type": 0,
                "ATFD_type": 0,
                "DIT_type": 0,
                "FANOUT_type": 0,
                "FANOUT_method": 0,
                "ATLD_method": 0,
                "CFNAMM_method": 0.0,
                "Error": f"Archive extraction or file search failed: {str(e)}"
            }])