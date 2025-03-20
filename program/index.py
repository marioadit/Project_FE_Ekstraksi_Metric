import streamlit as st
from . import controller as ct

def main():
    st.title("Kotlin Function Extractor")

    file = st.file_uploader("Upload a RAR or ZIP file containing Kotlin files", type=["rar", "zip"])

    if file is not None:
        df = ct.extract_and_parse(file)
        if isinstance(df, str):
            st.error(f"Error extracting archive: {df}")
        else:
            st.dataframe(df)


if __name__ == "__main__":
    main()