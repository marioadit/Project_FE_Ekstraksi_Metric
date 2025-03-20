# CHECKPOINT 1
import os  # Mengimpor modul os untuk berinteraksi dengan sistem operasi, seperti file dan direktori
import re  # Mengimpor modul re untuk melakukan operasi regular expression, yang digunakan untuk pencarian pola dalam string
import zipfile  # Mengimpor modul zipfile untuk mengelola file ZIP, termasuk ekstraksi dan pembuatan file ZIP
import json  # Mengimpor modul json untuk memanipulasi data dalam format JSON (JavaScript Object Notation)
import streamlit as st  # Mengimpor modul streamlit dan memberinya alias 'st' untuk membuat aplikasi web interaktif
import tempfile  # Mengimpor modul tempfile untuk membuat direktori sementara
import math  # Mengimpor modul math untuk operasi matematika, seperti penghitungan angka
#from program import index
from PIL import (
    Image,
)  # Mengimpor kelas Image dari modul PIL (Python Imaging Library) untuk manipulasi gambar
from streamlit_option_menu import (
    option_menu,
)  # Mengimpor fungsi option_menu untuk membuat menu navigasi yang lebih interaktif di Streamlit
import pandas as pd  # Mengimpor modul pandas dan memberinya alias 'pd' untuk analisis data dan manipulasi data tabel
import shutil
from io import BytesIO
from datetime import (
    datetime,
)  # Mengimpor kelas datetime dari modul datetime untuk mendapatkan informasi tentang tanggal dan waktu saat ini


def analyze_kotlin_files(directory):
    # Inisialisasi variabel untuk menghitung jumlah file, kelas, fungsi, properti, dan paket
    file_count = 0
    class_count = 0
    function_count = 0
    property_count = 0
    packages = set()  # Set untuk menyimpan nama-nama paket
    package_dict = {}  # Dictionary untuk menyimpan detail dari setiap paket

    # Menelusuri direktori untuk mencari file .kt
    for root, dirs, files_in_dir in os.walk(directory):
        for file in files_in_dir:
            if file.endswith(
                ".kt"
            ):  # Hanya memproses file dengan ekstensi .kt (Kotlin)
                file_count += 1
                file_path = os.path.join(root, file)

                # Membaca isi file
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                    # Menggunakan regex untuk menemukan kelas, fungsi, dan properti dalam file
                    found_classes = re.findall(r"class\s+\w+", content)
                    found_functions = re.findall(r"fun\s+\w+", content)
                    found_properties = re.findall(r"val\s+\w+|var\s+\w+", content)

                    # Memperbarui jumlah total kelas, fungsi, dan properti
                    class_count += len(found_classes)
                    function_count += len(found_functions)
                    property_count += len(found_properties)

                    # Menemukan nama paket dalam file (jika ada)
                    package_name = re.search(r"package\s+([\w\.]+)", content)
                    package = package_name.group(1) if package_name else "default"
                    packages.add(package)  # Menambahkan paket ke dalam set

                    # Jika paket belum ada di dalam dictionary, inisialisasi entri baru
                    if package not in package_dict:
                        package_dict[package] = {
                            "files": [],
                            "classes": [],
                            "functions": [],
                            "properties": [],
                        }

                    # Menambahkan informasi file, kelas, fungsi, dan properti ke dictionary paket
                    package_dict[package]["files"].append(file)
                    package_dict[package]["classes"].extend(found_classes)
                    package_dict[package]["functions"].extend(found_functions)
                    package_dict[package]["properties"].extend(found_properties)

    # Mengembalikan hasil analisis dalam bentuk dictionary
    return {
        "number of files": file_count,  # Total file Kotlin yang dianalisis
        "number of classes": class_count,  # Total kelas yang ditemukan
        "number of functions": function_count,  # Total fungsi yang ditemukan
        "number of properties": property_count,  # Total properti yang ditemukan
        "number of packages": len(packages),  # Total paket yang ditemukan
        "Packages": package_dict,  # Dictionary yang berisi detail paket, file, kelas, dll.
    }


# # Fungsi untuk memecah konten file menjadi per fungsi
# def extract_function_content(content, function_name):
#     # Regex untuk mengekstrak isi fungsi dari nama fungsi yang diberikan
#     function_regex = rf"fun\s+{function_name}\s*\(.*?\)\s*{{(.*?)}}"
#     match = re.search(function_regex, content, re.DOTALL)
#     if match:
#         return match.group(1)  # Mengembalikan isi dari fungsi
#     return ""


def extract_function_content(content, function_name):
    # Mencari fungsi dengan nama tertentu
    start_idx = content.find(f"fun {function_name}(")
    if start_idx == -1:
        return ""

    # Menemukan posisi kurung kurawal pertama
    start_idx = content.find("{", start_idx)
    if start_idx == -1:
        return ""

    # Stack untuk melacak kurung kurawal bersarang
    stack = []
    function_body = []

    # Memulai pemrosesan dari posisi kurung pertama
    for idx, char in enumerate(content[start_idx:], start=start_idx):
        if char == "{":
            stack.append("{")
        elif char == "}":
            stack.pop()

        # Menambahkan karakter ke body fungsi jika stack tidak kosong
        function_body.append(char)

        # Ketika stack kosong, kita sudah sampai akhir fungsi
        if not stack:
            break

    return "".join(function_body).strip()


# # Fungsi untuk menghitung NOLV_METHOD (jumlah variabel lokal)
# def calculate_nolv(function_content):
#     # Mencari semua deklarasi variabel lokal yang menggunakan 'val' atau 'var'
#     local_variables = re.findall(r"\b(val|var)\s+\w+", function_content)
#     return len(local_variables)


# # Fungsi untuk menghitung NOLV_METHOD (jumlah variabel lokal)
# def calculate_nolv(function_content):
#     # Mencari semua deklarasi variabel lokal yang menggunakan 'val' atau 'var'
#     # serta variabel yang langsung diinstansiasi dengan objek.
#     local_variables = re.findall(
#         r"\b(?:val|var)\s+\w+|(?<!val|var)\s+\w+\s*=\s*[\w\.]+\s*\(.*?\)",
#         function_content,
#     )
#     return len(local_variables)


# # Fungsi untuk menghitung NOLV_METHOD (jumlah variabel lokal)
# def calculate_nolv(function_content):
#     # Mencari semua deklarasi variabel lokal yang menggunakan 'val' atau 'var'
#     # serta variabel yang diinstansiasi dengan objek (misalnya BatteryFragment())
#     local_variables = re.findall(
#         r"\b(?:val|var)\s+\w+\s*=\s*.*?|\b(?:val|var)\s+\w+|\w+\s*=\s*\w+\s*\(.*?\)",
#         function_content,
#     )
#     return len(local_variables)


def calculate_nolv(function_content):
    # Memecah kode menjadi baris-baris
    lines = function_content.split("\n")
    local_variables = set()

    # Memeriksa setiap baris untuk menemukan deklarasi variabel lokal
    for line in lines:
        line = line.strip()

        # Mencari 'val' atau 'var' untuk deklarasi variabel lokal
        if line.startswith("val") or line.startswith("var"):
            parts = line.split("=")
            if len(parts) > 1:
                variable = parts[0].strip().split()[-1]  # Mendapatkan nama variabel
                local_variables.add(variable)

    return len(local_variables)


# Contoh penggunaan dengan kode dalam metode 'onCreate'
method_content = """
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)

    Realm.init(this)
    Realm.compactRealm(Realm.getDefaultConfiguration()!!)

    _binding = ActivityMainBinding.inflate(layoutInflater)
    setContentView(binding.root)

    val batteryEnabled = PreferenceManager.getDefaultSharedPreferences(this).getBoolean("batteryEnabled", false)
    val bikeEnabled = PreferenceManager.getDefaultSharedPreferences(this).getBoolean("bikeEnabled", false)

    if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
        requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION), 4711)
    } else {
        if (batteryEnabled) {
            Intent(this, BmsService::class.java).also { intent -> startService(intent) }
        }

        if (bikeEnabled) {
            Intent(this, BikeService::class.java).also { intent -> startService(intent) }
        }

        Intent(this, BleService::class.java).also { intent -> startService(intent) }
    }

    val batteryFragment = BatteryFragment()
    val bikeFragment = BikeFragment()
    val statsFragment = StatsFragment()
    val settingsFragment = SettingsFragment()

    binding.bottomNavigation.setOnNavigationItemSelectedListener {
        when (it.itemId) {
            R.id.page_battery -> supportFragmentManager.beginTransaction().apply { replace(R.id.nav_host_fragment, batteryFragment).commit() }
            R.id.page_bike -> supportFragmentManager.beginTransaction().apply { replace(R.id.nav_host_fragment, bikeFragment).commit() }
            R.id.page_stats -> supportFragmentManager.beginTransaction().apply { replace(R.id.nav_host_fragment, statsFragment).commit() }
            R.id.page_settings -> supportFragmentManager.beginTransaction().apply { replace(R.id.nav_host_fragment, settingsFragment).commit() }
        }
        true
    }
}
"""

# Menghitung NOLV untuk metode onCreate
nolv = calculate_nolv(method_content)
print(f"Total NOLV: {nolv}")


# Fungsi untuk menghitung CYCLO_METHOD (kompleksitas siklomatik)
def calculate_cyclomatic_complexity(function_content):
    # Mencari semua cabang logis dalam konten menggunakan kata kunci kontrol alur
    logical_branches = re.findall(
        r"\b(if|else|for|while|when|switch|case|try|catch)\b", function_content
    )
    return len(logical_branches) + 1  # +1 untuk fungsi itu sendiri


# Fungsi untuk menghitung NUMBER_CONSTRUCTOR_NOTDEFAULTCONSTRUCTOR_METHOD
def count_non_default_constructors(content, class_name):
    # Mencari konstruktor dalam kelas dengan nama class_name
    constructors = re.findall(
        rf"class\s+{class_name}\s*.*?\((.*?)\)", content, re.DOTALL
    )
    non_default_constructors = 0  # Inisialisasi penghitung konstruktor non-default
    for constructor in constructors:
        # Jika ada parameter dalam konstruktor, itu berarti konstruktor non-default
        if constructor and not re.match(r"\s*\)", constructor):
            non_default_constructors += 1
    return non_default_constructors  # Mengembalikan jumlah konstruktor non-default


# Fungsi untuk mencari semua fungsi dalam konten file Kotlin
def find_functions(content):
    # Mengembalikan semua nama fungsi yang ditemukan dalam konten
    return re.findall(r"fun\s+(\w+)\s*\(", content)


# Fungsi untuk mencari semua kelas dalam konten file Kotlin
def find_classes(content):
    # Mengembalikan semua nama kelas yang ditemukan dalam konten
    return re.findall(r"class\s+(\w+)", content)


# Fungsi untuk menghapus semua file di dalam direktori
def clear_directory(directory):
    if os.path.exists(directory):
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}. Reason: {e}")


# Fungsi untuk membaca zip dan mengolah file Kotlin secara per function
def analyze_kotlin_files_per_function(zip_file, project_name):
    clear_directory("kotlin_files")  # Membersihkan folder sebelum ekstraksi
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        zip_ref.extractall("kotlin_files")  # Mengekstrak semua file ZIP ke dalam folder

    packages = set()  # Set untuk menyimpan nama paket unik
    results = []  # List untuk menyimpan hasil analisis
    extraction_date = datetime.now().strftime(
        "%Y-%m-%d"
    )  # Mendapatkan tanggal ekstraksi

    # Iterasi melalui semua file dalam direktori kotlin_files
    for root, _, files in os.walk("kotlin_files"):
        for file in files:
            if file.endswith(".kt"):  # Memeriksa apakah file adalah file Kotlin
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()  # Membaca konten file

                # Mencari nama paket dalam file Kotlin
                package_name = re.search(r"package\s+([\w\.]+)", content)
                package = (
                    package_name.group(1) if package_name else "default"
                )  # Menentukan paket
                packages.add(package)  # Menambahkan nama paket ke set

                # Mencari semua kelas dalam konten file
                classes = find_classes(content)
                for class_name in classes:
                    # Menghitung konstruktor non-default untuk kelas tersebut
                    non_default_constructors = count_non_default_constructors(
                        content, class_name
                    )

                    # Mencari semua fungsi dalam konten file
                    functions = find_functions(content)
                    for function in functions:
                        # Mengambil isi dari fungsi yang sedang dianalisis
                        function_content = extract_function_content(content, function)

                        # Menghitung metrik untuk setiap fungsi
                        nolv = calculate_nolv(function_content)
                        cyclo = calculate_cyclomatic_complexity(function_content)

                        # Menyimpan hasil analisis dalam bentuk dictionary
                        results.append(
                            {
                                "Extraction Date": extraction_date,
                                "Project": project_name,
                                "Package": package,
                                "Class": class_name,
                                "Function": function,
                                # "FunctionContent": function_content,  # Menambahkan kolom baru berisi isi fungsi
                                "NOLV_METHOD": nolv,
                                "CYCLO_METHOD": cyclo,
                                "NUMBER_CONSTRUCTOR_NOTDEFAULTCONSTRUCTOR_METHOD": non_default_constructors,
                            }
                        )
    return results  # Mengembalikan hasil analisis sebagai list of dictionaries


# Fungsi untuk mendownload data dalam bentuk CSV
def download_csv(df):
    # Konversi DataFrame ke CSV dalam bentuk bytes
    csv = df.to_csv(index=False).encode("utf-8")
    return csv  # Mengembalikan data CSV dalam bentuk bytes


# Function to extract ZIP files
def extract_zip(zip_file, extract_to):
    # Membuka file ZIP yang ditentukan dalam mode baca ("r").
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        # Mengekstrak semua isi file ZIP ke direktori yang ditentukan oleh parameter extract_to.
        zip_ref.extractall(
            extract_to
        )  # Menggunakan metode extractall() untuk mengekstrak seluruh isi file ZIP.


def calculate_cognitive_complexity(line):
    # Logika untuk menghitung kompleksitas kognitif
    complexity = 0
    # Memeriksa apakah ada struktur kontrol dalam baris
    if any(
        keyword in line
        for keyword in [
            "if",  # Percabangan jika
            "else",  # Percabangan lain
            "for",  # Perulangan untuk
            "while",  # Perulangan selama
            "do",  # Perulangan do-while
            "when",  # Percabangan ketika
            "switch",  # Percabangan switch
            "case",  # Kasus dalam switch
            "try",  # Blok percobaan
            "catch",  # Menangkap exception
        ]
    ):
        complexity += 1  # Tingkatkan kompleksitas untuk setiap struktur kontrol
    return complexity


def calculate_mcc(line):
    # Logika untuk menghitung kompleksitas siklomatik
    count = 0
    # Memeriksa apakah ada struktur kontrol dalam baris
    if any(
        keyword in line
        for keyword in [
            "if",  # Percabangan jika
            "else",  # Percabangan lain
            "for",  # Perulangan untuk
            "while",  # Perulangan selama
            "do",  # Perulangan do-while
            "when",  # Percabangan ketika
            "switch",  # Percabangan switch
            "case",  # Kasus dalam switch
            "try",  # Blok percobaan
            "catch",  # Menangkap exception
        ]
    ):
        count += 1  # Hitung cabang
    return count


def identify_code_smells(lines):
    # Fungsi untuk mengidentifikasi code smells
    smells = 0
    # Memeriksa setiap baris dalam kode
    for line in lines:
        # Contoh smell: metode yang terlalu panjang
        if (
            len(line.strip()) > 100
        ):  # Menghitung jika panjang baris lebih dari 100 karakter
            smells += 1  # Tingkatkan jumlah code smells
    return smells


# Fungsi untuk menghitung laporan kompleksitas
def calculate_complexity_report(directory):
    loc = 0  # Total baris kode
    sloc = 0  # Total baris kode sumber
    lloc = 0  # Total baris logis
    cloc = 0  # Total baris komentar
    cognitive_complexity = 0  # Kompleksitas kognitif
    code_smells = 0  # Jumlah code smells
    comment_ratio = 0  # Rasio komentar
    mcc_count = 0  # Hitungan kompleksitas siklomatik
    total_code_smells = 0  # Total code smells terdeteksi

    # Menelusuri direktori untuk mencari file .kt
    for root, dirs, files_in_dir in os.walk(directory):
        for file in files_in_dir:
            if file.endswith(".kt"):  # Memeriksa file Kotlin
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()  # Membaca semua baris dalam file

                    # Menghitung total baris kode (loc)
                    loc += len(lines)

                    # Menghitung kode sumber (sloc), baris logis (lloc), dan komentar (cloc)
                    for line in lines:
                        stripped_line = (
                            line.strip()
                        )  # Menghapus spasi di awal dan akhir
                        if stripped_line.startswith("//"):
                            cloc += 1  # Menghitung baris komentar
                        elif stripped_line != "":
                            sloc += 1  # Menghitung baris sumber
                            lloc += 1  # Menghitung setiap baris non-kosong sebagai baris logis

                            # Menghitung kompleksitas kognitif dan MCC
                            cognitive_complexity += calculate_cognitive_complexity(
                                stripped_line
                            )
                            mcc_count += calculate_mcc(stripped_line)

                    # Menghitung total code smells
                    total_code_smells += identify_code_smells(lines)

    # Menghitung metrik
    if lloc > 0:
        comment_ratio = (
            (cloc / sloc) * 100 if sloc > 0 else 0
        )  # Menghitung rasio komentar
        mcc_per_1000_lloc = (
            (mcc_count / (lloc / 1000)) if lloc > 0 else 0
        )  # MCC per 1000 baris logis
        code_smells_per_1000_lloc = (
            (total_code_smells / (lloc / 1000)) if lloc > 0 else 0
        )  # Code smells per 1000 baris logis

    # Mengembalikan hasil laporan kompleksitas
    return {
        "loc": loc,  # Total baris kode
        "sloc": sloc,  # Total baris sumber
        "lloc": lloc,  # Total baris logis
        "cloc": cloc,  # Total baris komentar
        "cognitive_complexity": cognitive_complexity,  # Kompleksitas kognitif
        "code_smells": total_code_smells,  # Total code smells
        "comment_ratio": comment_ratio,  # Rasio komentar
        "mcc_per_1000_lloc": mcc_per_1000_lloc,  # MCC per 1000 baris logis
        "code_smells_per_1000_lloc": code_smells_per_1000_lloc,  # Code smells per 1000 baris logis
    }


# Fungsi untuk menampilkan halaman ringkasan laporan
def show_summary_report_page():
    st.title("Summary Report")  # Menampilkan judul halaman

    # Input untuk mengunggah file ZIP
    uploaded_file = st.file_uploader(
        "Upload a ZIP file containing Kotlin files", type="zip"
    )

    if uploaded_file is not None:  # Jika file diunggah
        # Menggunakan direktori sementara untuk mengekstrak file ZIP
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(
                temp_dir, uploaded_file.name
            )  # Membuat path lengkap untuk file ZIP yang diunggah

            # Menyimpan file ZIP yang diunggah
            with open(zip_path, "wb") as f:
                f.write(
                    uploaded_file.getbuffer()
                )  # Menyimpan konten file ke dalam direktori sementara

            # Mengekstrak file ZIP
            extract_zip(zip_path, temp_dir)

            # Menjalankan analisis file Kotlin
            results = analyze_kotlin_files(temp_dir)

            # Menampilkan ringkasan laporan
            st.subheader("Summary Report:")  # Menampilkan subjudul
            st.write(
                "Number of Packages:", results["number of packages"]
            )  # Menampilkan jumlah paket
            st.write(
                "Number of Kotlin Files:", results["number of files"]
            )  # Menampilkan jumlah file Kotlin
            st.write(
                "Number of Classes:", results["number of classes"]
            )  # Menampilkan jumlah kelas
            st.write(
                "Number of Functions:", results["number of functions"]
            )  # Menampilkan jumlah fungsi
            st.write(
                "Number of Properties:", results["number of properties"]
            )  # Menampilkan jumlah properti

            # Penjelasan untuk setiap metrik dalam Bahasa Indonesia
            st.subheader("Penjelasan Metrik:")  # Menampilkan subjudul penjelasan metrik
            st.write(
                """
            **1. Lines of Code (LOC)**: Total baris kode, termasuk baris kosong dan komentar. Ini menunjukkan ukuran keseluruhan dari proyek.

            **2. Source Lines of Code (SLOC)**: Baris kode sumber yang sebenarnya, tanpa menghitung baris kosong atau komentar. Ini menunjukkan kode yang dieksekusi.

            **3. Logical Lines of Code (LLOC)**: Baris logis dari kode yang mengekspresikan satu operasi, seperti satu pernyataan. Ini memberikan gambaran yang lebih tepat tentang kompleksitas fungsional kode.

            **4. Comment Lines of Code (CLOC)**: Jumlah baris yang berisi komentar. Komentar membantu pengembang lain memahami kode, sehingga persentase yang sehat dari CLOC penting.

            **5. Cognitive Complexity**: Mengukur betapa sulitnya memahami kode secara keseluruhan. Nilai yang lebih tinggi berarti kode lebih sulit dipahami.

            **6. Code Smells**: Jumlah potensi masalah di kode yang dapat mengindikasikan kebutuhan perbaikan (misalnya, duplikasi kode, kode yang terlalu panjang, dll.).

            **7. Comment Source Ratio**: Persentase baris komentar dibandingkan dengan kode sumber. Persentase ini menunjukkan seberapa baik kode terdokumentasi.

            **8. MCC (McCabe Cyclomatic Complexity) per 1,000 LLOC**: Mengukur kompleksitas jalur kode berdasarkan jumlah cabang logika (if, while, dll.). Nilai yang lebih tinggi menunjukkan kode yang lebih sulit untuk diuji dan dipelihara.

            **9. Code Smells per 1,000 LLOC**: Rasio jumlah code smells per 1.000 baris logis. Semakin tinggi angkanya, semakin besar kemungkinan ada masalah kualitas kode.
            """
            )

# Fungsi untuk menampilkan laporan detail
def show_detailed_report_page():
    st.title("Detailed Report - Grouped by Package")  # Menampilkan judul halaman

    # Input untuk mengunggah file ZIP
    uploaded_file = st.file_uploader(
        "Upload a ZIP file containing Kotlin files", type="zip"
    )

    if uploaded_file is not None:  # Jika file diunggah
        # Menggunakan direktori sementara untuk mengekstrak file ZIP
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(
                temp_dir, uploaded_file.name
            )  # Membuat path lengkap untuk file ZIP yang diunggah

            # Menyimpan file ZIP yang diunggah
            with open(zip_path, "wb") as f:
                f.write(
                    uploaded_file.getbuffer()
                )  # Menyimpan konten file ke dalam direktori sementara

            # Mengekstrak file ZIP
            extract_zip(zip_path, temp_dir)

            # Menjalankan analisis file Kotlin
            results = analyze_kotlin_files(temp_dir)

            # Menampilkan rincian yang dikelompokkan berdasarkan paket
            st.subheader("Details by Package")  # Menampilkan subjudul

            for index, (package, details) in enumerate(
                results["Packages"].items(), start=1
            ):
                st.write(f"**Package {index}:** {package}")  # Menampilkan nama paket
                st.write(
                    f"**Files ({len(details['files'])}):** {details['files']}"
                )  # Menampilkan daftar file dalam paket
                st.write(
                    f"**Classes ({len(details['classes'])}):** {details['classes']}"
                )  # Menampilkan daftar kelas dalam paket
                st.write(
                    f"**Functions ({len(details['functions'])}):** {details['functions']}"
                )  # Menampilkan daftar fungsi dalam paket
                st.write(
                    f"**Properties ({len(details['properties'])}):** {details['properties']}"
                )  # Menampilkan daftar properti dalam paket
                st.write("---")  # Menampilkan garis pemisah


# Fungsi untuk menampilkan halaman laporan kompleksitas
def show_complexity_report_page():
    st.title("Complexity Report")  # Menampilkan judul halaman

    # Input untuk mengunggah file ZIP
    uploaded_file = st.file_uploader(
        "Upload a ZIP file containing Kotlin files", type="zip"
    )

    if uploaded_file is not None:  # Jika file diunggah
        # Menggunakan direktori sementara untuk mengekstrak file ZIP
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(
                temp_dir, uploaded_file.name
            )  # Membuat path lengkap untuk file ZIP yang diunggah

            # Menyimpan file ZIP yang diunggah
            with open(zip_path, "wb") as f:
                f.write(
                    uploaded_file.getbuffer()
                )  # Menyimpan konten file ke dalam direktori sementara

            # Mengekstrak file ZIP
            extract_zip(zip_path, temp_dir)

            # Menjalankan analisis laporan kompleksitas
            results = calculate_complexity_report(temp_dir)

            # Menampilkan laporan kompleksitas
            st.subheader("Complexity Report:")  # Menampilkan subjudul
            st.write(
                "Total Lines of Code (LOC):", results["loc"]
            )  # Menampilkan total baris kode
            st.write(
                "Source Lines of Code (SLOC):", results["sloc"]
            )  # Menampilkan baris kode sumber
            st.write(
                "Logical Lines of Code (LLOC):", results["lloc"]
            )  # Menampilkan baris logis kode
            st.write(
                "Comment Lines of Code (CLOC):", results["cloc"]
            )  # Menampilkan baris komentar kode
            st.write(
                "Cognitive Complexity:", results["cognitive_complexity"]
            )  # Menampilkan kompleksitas kognitif
            st.write(
                "Number of Total Code Smells:", results["code_smells"]
            )  # Menampilkan jumlah code smells
            st.write(
                "Comment Source Ratio (%):", results["comment_ratio"]
            )  # Menampilkan rasio komentar terhadap kode sumber
            st.write(
                "MCC per 1,000 LLOC:", results["mcc_per_1000_lloc"]
            )  # Menampilkan MCC per 1.000 LLOC
            st.write(
                "Code Smells per 1,000 LLOC:", results["code_smells_per_1000_lloc"]
            )  # Menampilkan code smells per 1.000 LLOC


# Fungsi untuk menampilkan halaman Download Report
def show_download_report_page():
    st.header("Download Report")

    project_name = st.text_input("Project Name")
    uploaded_zip = st.file_uploader("Upload Kotlin ZIP", type="zip")

    if uploaded_zip and project_name:
        st.success("File uploaded successfully")
        results = analyze_kotlin_files_per_function(
            BytesIO(uploaded_zip.read()), project_name
        )

        if results:
            df = pd.DataFrame(results)

            total_nolv = df["NOLV_METHOD"].sum()
            total_cyclo = df["CYCLO_METHOD"].sum()
            total_not_default_constructors = df[
                "NUMBER_CONSTRUCTOR_NOTDEFAULTCONSTRUCTOR_METHOD"
            ].sum()

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Total NOLV_METHOD", value=total_nolv)
            with col2:
                st.metric(label="Total CYCLO_METHOD", value=total_cyclo)
            with col3:
                st.metric(
                    label="Total NUMBER_CONSTRUCTOR_NOTDEFAULTCONSTRUCTOR_METHOD",
                    value=total_not_default_constructors,
                )

            page_size = 100
            total_rows = len(df)
            total_pages = (total_rows // page_size) + (
                1 if total_rows % page_size > 0 else 0
            )
            page_number = st.number_input(
                "Page Number", min_value=1, max_value=total_pages, value=1
            )
            start_row = (page_number - 1) * page_size
            end_row = start_row + page_size

            st.write(df[start_row:end_row])

            csv_data = download_csv(df)
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name="kotlin_metrics_report.csv",
                mime="text/csv",
            )

            st.info(f"Displaying rows {start_row + 1} to {end_row}")
    else:
        st.warning("Please enter a project name and upload a Kotlin zip file.")


# Fungsi utama untuk menjalankan aplikasi Streamlit
def main():
    # Menambahkan sidebar yang lebih interaktif menggunakan `streamlit-option-menu`
    page = style_sidebar()  # Mengatur sidebar

    # Menampilkan


# Fungsi untuk memberi gaya pada sidebar menggunakan `streamlit-option-menu`
def style_sidebar():
    """
    Fungsi ini digunakan untuk mendesain sidebar menggunakan opsi menu Streamlit.

    Returns:
    str: Opsi menu yang dipilih oleh pengguna.
    """
    with st.sidebar:
        selected = option_menu(
            menu_title="Navigation",  # Judul menu
            options=[
                "AST",
                "Summary Report",  # Pilihan laporan ringkasan
                "Detailed Report",  # Pilihan laporan detail
                "Complexity Report",  # Pilihan laporan kompleksitas
                "Download Report",  # Pilihan laporan unduh
            ],
            icons=[
                "graph-up",  # Ikon untuk laporan ringkasan
                "list-task",  # Ikon untuk laporan detail
                "bar-chart",  # Ikon untuk laporan kompleksitas
                "download",  # Ikon untuk laporan unduh
            ],
            menu_icon="menu-button-wide",  # Ikon untuk judul menu
            default_index=0,  # Indeks default (dimulai dari 0)
            orientation="vertical",  # Orientasi menu secara vertikal
            styles={
                "container": {
                    "padding": "5px",
                    "background-color": "#f0f0f0",
                },  # Gaya kontainer sidebar
                "icon": {"color": "#FF4B4B", "font-size": "25px"},  # Gaya ikon
                "nav-link": {
                    "font-size": "18px",  # Gaya teks link navigasi
                    "text-align": "left",  # Rata kiri untuk teks link
                    "margin": "0px",  # Margin nol untuk teks link
                    "--hover-color": "#eee",  # Warna latar belakang saat hover
                },
                "nav-link-selected": {
                    "background-color": "#FF4B4B"
                },  # Gaya untuk link yang dipilih
            },
        )
    return selected  # Mengembalikan opsi yang dipilih

import sys
# Tambahkan folder induk ke path agar Python bisa mengenali 'program' sebagai modul
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from program import index

def show_ast_page():
    index.main()  # Menjalankan fungsi utama dari program AST

# Fungsi utama untuk menjalankan aplikasi Streamlit
def main():
    # Menambahkan sidebar yang lebih interaktif menggunakan `streamlit-option-menu`
    page = style_sidebar()  # Mengatur sidebar

    # Menampilkan halaman berdasarkan pilihan sidebar
    if page == "Summary Report":  # Jika pilihan adalah laporan ringkasan
        show_summary_report_page()  # Menampilkan halaman laporan ringkasan
    elif page == "Detailed Report":  # Jika pilihan adalah laporan detail
        show_detailed_report_page()  # Menampilkan halaman laporan detail
    elif page == "Complexity Report":  # Jika pilihan adalah laporan kompleksitas
        show_complexity_report_page()  # Menampilkan halaman laporan kompleksitas
    elif page == "Download Report":  # Jika pilihan adalah laporan unduh
        show_download_report_page()  # Menampilkan halaman laporan unduh
    elif page == "AST":
        show_ast_page()


# Memeriksa apakah skrip dijalankan secara langsung
if __name__ == "__main__":
    main()  # Menjalankan fungsi utama
# END CHECKPOINT 1
