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
    """
    Count Access to Foreign Data (ATFD) by scanning for external class field/method accesses.
    Only counts the full chain of foreign accesses (e.g., batteryData.watthours.roundToInt counts as 1).
    """
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        return 0

    # Get current class field names
    current_fields = set()
    for member in class_declaration.body.members:
        if isinstance(member, node.PropertyDeclaration):
            decl = member.declaration
            if isinstance(decl, node.VariableDeclaration):
                current_fields.add(decl.name)
            elif isinstance(decl, node.MultiVariableDeclaration):
                for var in decl.sequence:
                    current_fields.add(var.name)

    foreign_accesses = set()
    code_str = str(class_declaration.body)

    # First, find all potential foreign access chains
    potential_chains = []
    current_chain = []
    in_chain = False

    # Simple tokenizer that preserves dots and identifiers
    tokens = []
    current_token = ""
    for char in code_str:
        if char.isalnum() or char == '.' or char == '_':
            current_token += char
        else:
            if current_token:
                tokens.append(current_token)
                current_token = ""
            if char != ' ':
                tokens.append(char)  # preserve other characters as separate tokens

    # Find all dot-separated chains
    for i, token in enumerate(tokens):
        if '.' in token and not token.startswith(('"', "'")):
            parts = token.split('.')
            # Only consider if the first part is a potential foreign object
            if parts[0] not in current_fields and parts[0] not in ('this', 'super'):
                potential_chains.append(token)

    # Now process the chains to find the longest unique foreign access
    for chain in potential_chains:
        parts = chain.split('.')
        # Find the longest unique foreign chain
        for i in range(1, len(parts)):
            sub_chain = '.'.join(parts[:i+1])
            # Check if this is a foreign access (first part not from current class)
            if parts[0] not in current_fields and parts[0] not in ('this', 'super'):
                # Remove any shorter chains that are prefixes of this one
                foreign_accesses = {ac for ac in foreign_accesses 
                                  if not ac.startswith(sub_chain + '.') and ac != sub_chain}
                foreign_accesses.add(sub_chain)
                break

    # Additional checks for method calls without dots (like getStringExtra())
    for line in code_str.split('\n'):
        # Common Android patterns
        android_patterns = [
            'getStringExtra', 'getIntExtra', 'getSerializableExtra',
            'getSharedPreferences', 'getSystemService', 'findViewById',
            'getItemAtPosition'
        ]
        
        for pattern in android_patterns:
            if pattern + '(' in line:
                # Check if it's a method call on some object
                if '.' + pattern + '(' in line:
                    # Get the full access chain
                    start = line.find('.') + 1
                    end = line.find('(')
                    full_access = line[start:end].strip()
                    if full_access not in current_fields:
                        foreign_accesses.add(full_access)
                else:
                    # Check if it's called on an object we already have in our chains
                    # If not, count as separate access
                    if not any(pattern in ac for ac in foreign_accesses):
                        foreign_accesses.add(pattern)

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

# KAMUS UNTUK PERKIRAAN DIT BERBASIS NAMA KELAS
# Nilai ini adalah perkiraan dan bisa Anda sesuaikan/tambahkan.
PREDEFINED_DIT_MAP = {
    # Android Core & AppCompat
    "Object": 0,
    "Any": 0,
    "Context": 1,
    "Application": 2,
    "Activity": 2,
    "Fragment": 1,
    "Service": 2,
    "BroadcastReceiver": 1,
    "ContentProvider": 2,
    "ViewModel": 1,
    "LiveData": 1,
    "RecyclerView": 2,
    "Adapter": 2, # RecyclerView.Adapter
    "ViewHolder": 1, # RecyclerView.ViewHolder
    
    # AppCompat & Material
    "AppCompatActivity": 3,
    "FragmentActivity": 2,
    "MaterialAlertDialogBuilder": 2,
    "DialogFragment": 2,
    "BottomSheetDialogFragment": 3,
    
    # Coroutines
    "CoroutineScope": 1,
    
    # Common Java
    "Exception": 1,
    "RuntimeException": 2,
    "Thread": 1,
}

def count_dit_by_name(class_declaration) -> int:
    """
    Memperkirakan DIT berdasarkan nama superclass menggunakan kamus yang telah ditentukan.
    """
    if not hasattr(class_declaration, 'supertypes') or not class_declaration.supertypes:
        return 0

    max_depth = 0
    
    for supertype_node in class_declaration.supertypes:
        parent_name = None
        delegate = getattr(supertype_node, 'delegate', None)
        
        if isinstance(delegate, node.ConstructorInvocation):
            parent_name = str(delegate.invoker)
        elif isinstance(delegate, node.UserType):
            parent_name = str(delegate)

        if parent_name:
            # Hapus generic types jika ada (e.g., "Adapter<MyViewHolder>" -> "Adapter")
            clean_parent_name = parent_name.split('<')[0]
            
            # Cek di kamus
            if clean_parent_name in PREDEFINED_DIT_MAP:
                depth = 1 + PREDEFINED_DIT_MAP[clean_parent_name]
            else:
                # Jika tidak ada di kamus, anggap DIT-nya 1
                depth = 1
            
            if depth > max_depth:
                max_depth = depth

    # Jika tidak ada superclass yang dikenali, tapi ada supertypes, default ke 1
    if max_depth == 0 and class_declaration.supertypes:
        return 1
        
    return max_depth

def count_fanout_type(class_declaration, fanout_method_values):
    """
    Menghitung FANOUT_type dengan menjumlahkan semua FANOUT_method dalam sebuah kelas.
    
    Args:
        class_declaration: Deklarasi kelas dari parser kopyt
        fanout_method_values: Dictionary yang berisi nilai FANOUT_method per method
        
    Returns:
        int: Total FANOUT_type (sum of all FANOUT_method in the class)
    """
    if not hasattr(class_declaration, 'body') or class_declaration.body is None:
        return 0
        
    # Jika class_declaration adalah kelas yang valid, jumlahkan semua FANOUT_method-nya
    total_fanout = 0
    for member in class_declaration.body.members:
        if isinstance(member, node.FunctionDeclaration):
            method_name = member.name
            total_fanout += fanout_method_values.get(method_name, 0)
    
    return total_fanout

def extracted_method(file_path):
    """
    Ekstrak informasi metode dan metrik dari satu file Kotlin.
    Fungsi ini lengkap dan menangani berbagai kasus.
    """
    results_for_file = []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        
        parser = Parser(code)
        ast = parser.parse()

        package_name = ast.package.name if ast.package else "Unknown"

        # Kasus 1: File tidak memiliki deklarasi kelas sama sekali
        if not ast.declarations:
            results_for_file.append({
                "Package": package_name, 
                "Class": "No Class Found", 
                "Method": "None", 
                "LOC": len(code.splitlines()), 
                "NOMNAMM_type": 0, "NOA_type": 0, "NIM_type": 0,
                "ATFD_type": 0, "DIT_type": 0, "FANOUT_type": 0,
                "FANOUT_method": 0, "ATLD_method": 0.0, "CFNAMM_method": 0.0,
                "Error": "No class declarations in file"
            })
            return results_for_file

        # Iterasi melalui semua deklarasi di file
        for class_declaration in ast.declarations:
            # Hanya proses deklarasi kelas, abaikan fungsi atau properti top-level
            if not isinstance(class_declaration, node.ClassDeclaration):
                continue

            class_name = class_declaration.name
            
            # --- Perhitungan Metrik Tingkat Kelas ---
            # Metrik ini dihitung sekali per kelas dan nilainya sama untuk semua baris method dari kelas tsb.
            dit_total = count_dit_by_name(class_declaration) #
            
            # Default values jika kelas tidak punya body
            nomnamm_total = 0
            noa_total = 0
            nim_total = 0
            atfd_total = 0
            cfnamm_results = {}
            fanout_method_values = {}
            class_fields = set()

            # Kasus 2: Kelas tidak punya body
            if not hasattr(class_declaration, 'body') or class_declaration.body is None:
                results_for_file.append({
                    "Package": package_name, "Class": class_name, "Method": "None", "LOC": 0,
                    "NOMNAMM_type": 0, "NOA_type": 0, "NIM_type": 0,
                    "ATFD_type": 0, "DIT_type": dit_total, "FANOUT_type": 0,
                    "FANOUT_method": 0, "ATLD_method": 0.0, "CFNAMM_method": 0.0,
                    "Error": "Class has no body"
                })
                continue # Lanjut ke deklarasi kelas berikutnya

            # Jika kelas punya body, hitung metrik tingkat kelas lainnya
            nomnamm_total = count_nomnamm_type(class_declaration) #
            noa_total = count_noa_type(class_declaration) #
            nim_total = count_nim_type(class_declaration) #
            atfd_total = count_atfd_type(class_declaration) #
            cfnamm_results = count_cfnamm_method(class_declaration) #

            # Kumpulkan properti kelas untuk perhitungan ATLD
            for member in class_declaration.body.members:
                if isinstance(member, node.PropertyDeclaration):
                    decl = member.declaration
                    if isinstance(decl, node.VariableDeclaration):
                        class_fields.add(decl.name)
                    elif isinstance(decl, node.MultiVariableDeclaration):
                        for var in decl.sequence:
                            class_fields.add(var.name)

            # --- Perhitungan Metrik Tingkat Method ---
            method_found_in_class = False
            for member in class_declaration.body.members:
                if isinstance(member, node.FunctionDeclaration):
                    method_found_in_class = True
                    function_name = member.name
                    body_str = str(member.body) if member.body else ""
                    
                    loc_count = body_str.count('\n') + 1 if body_str else 0
                    fanout_value = count_fanout_method(body_str, {m.name for m in class_declaration.body.members if isinstance(m, node.FunctionDeclaration)}) #
                    atld_value = count_atld_method(member, class_fields) #
                    cfnamm_value = cfnamm_results.get(function_name, 0.0) #
                    
                    fanout_method_values[function_name] = fanout_value

                    results_for_file.append({
                        "Package": package_name,
                        "Class": class_name,
                        "Method": function_name,
                        "LOC": loc_count,
                        "NOMNAMM_type": nomnamm_total,
                        "NOA_type": noa_total,
                        "NIM_type": nim_total,
                        "ATFD_type": atfd_total,
                        "DIT_type": dit_total,
                        "FANOUT_type": 0,  # Placeholder, akan diisi setelah loop
                        "FANOUT_method": fanout_value,
                        "ATLD_method": atld_value,
                        "CFNAMM_method": cfnamm_value,
                        "Error": ""
                    })

            # --- Finalisasi Metrik Tingkat Kelas (setelah semua method diproses) ---
            fanout_type_total = sum(fanout_method_values.values()) #

            # Kasus 3: Kelas punya body tapi tidak punya method
            if not method_found_in_class:
                class_loc = len(str(class_declaration.body).splitlines()) if class_declaration.body else 0
                results_for_file.append({
                    "Package": package_name, "Class": class_name, "Method": "None", "LOC": class_loc,
                    "NOMNAMM_type": nomnamm_total, "NOA_type": noa_total, "NIM_type": nim_total,
                    "ATFD_type": atfd_total, "DIT_type": dit_total, "FANOUT_type": fanout_type_total,
                    "FANOUT_method": 0, "ATLD_method": 0.0, "CFNAMM_method": 0.0,
                    "Error": "No methods found in class"
                })
            else:
                # Tambahkan nilai FANOUT_type ke semua baris method dari kelas ini
                for row in results_for_file:
                    if row["Class"] == class_name:
                        row["FANOUT_type"] = fanout_type_total

    except Exception as e:
        # Menangani error fatal saat parsing file
        results_for_file.append({
            "Package": "Error", "Class": os.path.basename(file_path), "Method": "Error", "LOC": 0,
            "NOMNAMM_type": 0, "NOA_type": 0, "NIM_type": 0,
            "ATFD_type": 0, "DIT_type": 0, "FANOUT_type": 0,
            "FANOUT_method": 0, "ATLD_method": 0.0, "CFNAMM_method": 0.0,
            "Error": f"Fatal parsing error: {str(e)}"
        })

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