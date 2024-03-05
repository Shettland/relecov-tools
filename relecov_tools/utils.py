#!/usr/bin/env python
"""
Common utility function used for relecov_tools package.
"""
import os
import glob
import hashlib
import logging
import questionary
import json
import openpyxl
import yaml
import gzip
import re
import shutil
from itertools import islice
from Bio import SeqIO
from rich.console import Console

log = logging.getLogger(__name__)


def file_exists(file_to_check):
    """
    Input:
        file_to_check   # file name to check if exists
    Return:
        True if exists
    """
    if os.path.isfile(file_to_check):
        return True
    return False


def safe_remove(file_path):
    try:
        os.remove(file_path)
    except OSError:
        return False
    return True


def get_files_match_condition(condition):
    """find all path names that matches with the condition"""
    return glob.glob(condition)


def read_json_file(j_file):
    """Read json file."""
    with open(j_file, "r") as fh:
        try:
            data = json.load(fh)
        except (UnicodeDecodeError, ValueError):
            raise

    return data


def read_excel_file(f_name, sheet_name, heading_row, leave_empty=True):
    """Read the input excel file and give the information in a list
    of dictionaries
    """
    wb_file = openpyxl.load_workbook(f_name, data_only=True)
    ws_metadata_lab = wb_file[sheet_name]
    heading = [i.value.strip() for i in ws_metadata_lab[heading_row] if i.value]
    ws_data = []
    for row in islice(ws_metadata_lab.values, heading_row, ws_metadata_lab.max_row):
        l_row = list(row)
        # Ignore the empty rows
        if all(cell is None for cell in l_row):
            continue
        data_row = {}
        for idx in range(0, len(heading)):
            if l_row[idx] is None:
                if leave_empty:
                    data_row[heading[idx]] = ""
                else:
                    data_row[heading[idx]] = "Not Provided [GENEPIO:0001668]"
            else:
                data_row[heading[idx]] = l_row[idx]
        ws_data.append(data_row)

    return ws_data


def read_csv_file_return_dict(file_name, sep, key_position=None):
    """Read csv or tsv file, according to separator, and return a dictionary
    where the main key is the first column, if key position is None otherwise
    the index value of the key position is used as key
    """
    try:
        with open(file_name, "r") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        raise
    heading = lines[0].strip().split(sep)
    if len(heading) == 1:
        return {"ERROR": "not valid format"}
    file_data = {}
    for line in lines[1:]:
        line_s = line.strip().split(sep)
        if key_position is None:
            file_data[line_s[0]] = {}
            for idx in range(1, len(heading)):
                file_data[line_s[0]][heading[idx]] = line_s[idx]
        else:
            file_data[line_s[key_position]] = {}
            for idx in range(len(heading)):
                if idx == key_position:
                    continue
                file_data[line_s[key_position]][heading[idx]] = line_s[idx]

    return file_data


def read_fasta_return_SeqIO_instance(file_name):
    """Read fasta and return SeqIO instance"""
    try:
        return SeqIO.read(file_name, "fasta")
    except FileNotFoundError:
        raise


def read_yml_file(file_name):
    """Read yml file"""
    with open(file_name, "r") as fh:
        try:
            return yaml.safe_load(fh)
        except yaml.YAMLError:
            raise


def get_md5_from_local_folder(local_folder):
    """Fetch the md5 values for each file in the file list"""
    md5_results = {}
    reg_for_md5 = os.path.join(local_folder, "*.md5")
    # reg_for_non_md5 = os.path.join(local_folder, "*[!.md5]")
    md5_files = glob.glob(reg_for_md5)
    if not md5_files:
        return False
    else:
        for md5_file in md5_files:
            file_path_name, f_ext = os.path.splitext(md5_file)
            if not file_exists(file_path_name):
                log.error("Found md5 file but not %s", file_path_name)
                continue
            file_name = os.path.basename(file_path_name)
            fh = open(md5_file, "r")
            md5_results[file_name] = fh.read()
            fh.close()
    return md5_results


def read_md5_checksum(file_name, avoid_chars=list()):
    """Read MD5_checksum file and return a dict of {file: md5_hash}

    Args:
        file_name (str): file containing "md5hash  file" in tab separated format
        avoid_chars (list(str), optional): Lines with any of these elements
        will be skipped. Defaults to list().

    Returns:
        hash_dict(dict): dictionary of {file: md5_hash}
    """
    try:
        with open(file_name, "r") as file:
            content = file.read()
    except FileNotFoundError:
        raise
    clean_content = content.replace("*", "")
    lines = clean_content.splitlines()
    translation = str.maketrans("", "", "'\"")
    if any("\t" in line for line in lines):
        lines = [line.strip().translate(translation).split("\t") for line in lines]
    elif any("," in line for line in lines):
        lines = [line.strip().translate(translation).split(",") for line in lines]
    else:
        lines = [line.strip().translate(translation).split("  ") for line in lines]
    clean_lines = [
        x for x in lines if not any(ch in string for ch in avoid_chars for string in x)
    ]
    # md5sum should always have 2 columns: hash - path
    md5_lines = [line for line in clean_lines if len(line) == 2]
    if not md5_lines:
        return False
    # split paths for both windows "\" and linux "/" using regex [\\/]
    hash_dict = {re.split(r"[\\/]", line[1])[-1]: line[0].lower() for line in md5_lines}
    return hash_dict


def delete_local_folder(folder):
    """Delete download folder because files does not complain requisites"""
    log.info("Deleting local folder %s", folder)
    shutil.rmtree(folder, ignore_errors=True)
    return True


def calculate_md5(file_name):
    """Calculate the md5 value for the file name"""
    return hashlib.md5(open(file_name, "rb").read()).hexdigest()


def write_md5_file(file_name, md5_value):
    """Write md5 to file"""
    with open(file_name, "w") as fh:
        fh.write(md5_value)
    return


def create_md5_files(local_folder, file_list):
    """Create the md5 files and return their value"""
    md5_results = {}
    for file_name in file_list:
        md5_results[file_name] = [
            local_folder,
            calculate_md5(os.path.join(local_folder, file_name)),
        ]
        md5_file_name = file_name + ".md5"
        write_md5_file(
            os.path.join(local_folder, md5_file_name), md5_results[file_name][1]
        )
    return md5_results


def save_local_md5(file_name, md5_value):
    """Save the MD5 value"""
    with open(file_name, "w") as fh:
        fh.write(md5_value)
    return True


def write_json_fo_file(data, file_name):
    """Write metadata to json file"""
    with open(file_name, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=4, sort_keys=True, ensure_ascii=False))
    return True


def compress_file(file):
    """compress a given file with gzip, adding .gz extension afterwards

    Args:
        file (str): path to the given file
    """
    try:
        with open(file, "rb") as raw, gzip.open(f"{file}.gz", "wb") as comp:
            comp.writelines(raw)
        return True
    except FileNotFoundError:
        return False


def rich_force_colors():
    """
    Check if any environment variables are set to force Rich to use coloured output
    """
    if (
        os.getenv("GITHUB_ACTIONS")
        or os.getenv("FORCE_COLOR")
        or os.getenv("PY_COLORS")
    ):
        return True
    return None


stderr = Console(
    stderr=True, style="dim", highlight=False, force_terminal=rich_force_colors()
)


def prompt_text(msg):
    source = questionary.text(msg).unsafe_ask()
    return source


def prompt_password(msg):
    source = questionary.password(msg).unsafe_ask()
    return source


def prompt_tmp_dir_path():
    stderr.print("Temporal directory destination to execute service")
    source = questionary.path("Source path").unsafe_ask()
    return source


def prompt_selection(msg, choices):
    selection = questionary.select(msg, choices=choices).unsafe_ask()
    return selection


def prompt_path(msg):
    source = questionary.path(msg).unsafe_ask()
    return source


def prompt_yn_question(msg):
    confirmation = questionary.confirm(msg).unsafe_ask()
    return confirmation


def prompt_skip_folder_creation():
    stderr.print("Do you want to skip folder creation? (Y/N)")
    confirmation = questionary.confirm("Skip?", default=False).unsafe_ask()
    return confirmation


def prompt_checkbox(msg, choices):
    selected_options = questionary.checkbox(msg, choices=choices).unsafe_ask()
    return selected_options
