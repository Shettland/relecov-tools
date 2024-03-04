#!/usr/bin/env python
import os
import sys
import logging
import glob
import rich.console
from datetime import datetime
from yaml import YAMLError

import relecov_tools.utils
from relecov_tools.config_json import ConfigJson
from relecov_tools.long_table_parse import LongTableParse

# import relecov_tools.json_schema

log = logging.getLogger(__name__)
stderr = rich.console.Console(
    stderr=True,
    style="dim",
    highlight=False,
    force_terminal=relecov_tools.utils.rich_force_colors(),
)


class BioinfoMetadata:
    def __init__(
        self,
        json_file=None,
        input_folder=None,
        output_folder=None,
        software='viralrecon',
    ):
        if json_file is None:
            json_file = relecov_tools.utils.prompt_path(
                msg="Select the json file that was created by the read-lab-metadata"
            )
        if not os.path.isfile(json_file):
            log.error("json file %s does not exist ", json_file)
            stderr.print(f"[red] file {json_file} does not exist")
            sys.exit(1)
        self.json_file = json_file

        if input_folder is None:
            self.input_folder = relecov_tools.utils.prompt_path(
                msg="Select the input folder"
            )
        else:
            self.input_folder = input_folder
        if output_folder is None:
            self.output_folder = relecov_tools.utils.prompt_path(
                msg="Select the output folder"
            )
        else:
            self.output_folder = output_folder

        if software is None:
            software = relecov_tools.utils.prompt_path(
                msg="Select the software, pipeline or tool use in the bioinformatic analysis (available: 'viralrecon'): "
            )
        self.software_name = software

        json_file = os.path.join(os.path.dirname(__file__), "conf", "bioinfo_config.json")
        config_json = ConfigJson(json_file)
        self.configuration = config_json
        required_files = self.configuration.get_topic_data(
            self.software_name, "required_file"
        )
        self.req_files = {}
        for key, file in required_files.items():
            f_path = os.path.join(self.input_folder, file)
            if not os.path.isfile(f_path):
                log.error("File %s does not exist", file)
                stderr.print(f"[red]File {file} does not exist")
                sys.exit(1)
            self.req_files[key] = f_path

    def add_fixed_values(self, j_data, fixed_values):
        """include the fixed data defined in configuration or feed custom empty fields"""
        f_values = self.configuration.get_topic_data(self.software_name, fixed_values)
        for row in j_data:
            for field, value in f_values.items():
                row[field] = value
        return j_data

    def mapping_over_table(self, j_data, map_data, mapping_fields, table_name):
        """Auxiliar function to iterate over variants and mapping tables to map metadata"""
        errors = []
        field_errors = {}
        for row in j_data:
            sample_name = row["submitting_lab_sample_id"]
            if sample_name in map_data:
                for field, value in mapping_fields.items():
                    try:
                        row[field] = map_data[sample_name][value]
                    except KeyError as e:
                        field_errors[sample_name] = {field: e}
                        row[field] = "Not Provided [GENEPIO:0001668]"
                        continue
            else:
                errors.append(sample_name)
                for field in mapping_fields.keys():
                    row[field] = "Not Provided [GENEPIO:0001668]"
        if errors:
            lenerrs = len(errors)
            log.error(
                "{0} samples missing in {1}:\n{2}".format(lenerrs, table_name, errors)
            )
            stderr.print(f"[red]{lenerrs} samples missing in {table_name}:\n{errors}")
        if field_errors:
            log.error("Fields not found in {0}:\n{1}".format(table_name, field_errors))
            stderr.print(f"[red]Missing values in {table_name}\n:{field_errors}")
        return j_data

    def include_data_from_mapping_stats(self, j_data):
        """By processing mapping stats file the following information is
        included in schema properties:  depth_of_coverage_value, lineage_name,
        number_of_variants_in_consensus, number_of_variants_with_effect,
        per_genome_greater_10x. per_Ns. per_reads_host, per_reads_virus.
        per_unmapped, qc_filtered, reference_genome_accession
        """
        # position of the sample columns inside mapping file
        sample_position = 4
        map_data = relecov_tools.utils.read_csv_file_return_dict(
            self.req_files["mapping_stats"], sep="\t", key_position=sample_position
        )

        mapping_fields = self.configuration.get_topic_data(
            self.software_name, "mapping_stats"
        )
        j_data_with_mapping_stats = self.mapping_over_table(
            j_data, map_data, mapping_fields, "mapping stats"
        )
        return j_data_with_mapping_stats

    def include_pangolin_data(self, j_data):
        """Include pangolin data collecting form each file generated by pangolin"""
        mapping_fields = self.configuration.get_topic_data(
            self.software_name, "mapping_pangolin"
        )
        missing_pango = []
        for row in j_data:
            if "-" in row["submitting_lab_sample_id"]:
                sample_name = row["submitting_lab_sample_id"].replace("-", "_")
            else:
                sample_name = row["submitting_lab_sample_id"]

            f_name_regex = sample_name + ".pangolin*.csv"
            f_path = os.path.join(self.input_folder, f_name_regex)
            pango_files = glob.glob(f_path)
            if pango_files:
                if len(pango_files) > 1:
                    stderr.print(
                        "[yellow]More than one pangolin file found for sample",
                        f"[yellow]{sample_name}. Selecting the most recent one",
                    )
                try:
                    pango_files = sorted(
                        pango_files,
                        key=lambda dt: datetime.strptime(dt.split(".")[-2], "%Y%m%d"),
                    )
                    row["lineage_analysis_date"] = pango_files[0].split(".")[-2]
                except ValueError:
                    log.error("No date found in %s pangolin files", sample_name)
                    stderr.print(
                        f"[red]No date found in sample {sample_name}",
                        f"[red]pangolin filenames: {pango_files}",
                    )
                    stderr.print("[Yellow] Using mapping analysis date instead")
                    # If no date in pangolin files, set date as analysis date
                    row["lineage_analysis_date"] = row["analysis_date"]
                f_data = relecov_tools.utils.read_csv_file_return_dict(
                    pango_files[0], sep=","
                )
                pang_key = list(f_data.keys())[0]
                for field, value in mapping_fields.items():
                    row[field] = f_data[pang_key][value]
            else:
                missing_pango.append(sample_name)
                for field in mapping_fields.keys():
                    row[field] = "Not Provided [GENEPIO:0001668]"
        if len(missing_pango) >= 1:
            stderr.print(
                f"[yellow]{len(missing_pango)} samples missing pangolin.csv file:"
            )
            stderr.print(f"[yellow]{missing_pango}")
        return j_data

    def include_consensus_data(self, j_data):
        """Include genome length, name, file name, path and md5 by preprocessing
        each file of consensus.fa
        """

        mapping_fields = self.configuration.get_topic_data(
            self.software_name, "mapping_consensus"
        )
        missing_consens = []
        for row in j_data:
            if "-" in row["submitting_lab_sample_id"]:
                sample_name = row["submitting_lab_sample_id"].replace("-", "_")
            else:
                sample_name = row["submitting_lab_sample_id"]
            f_name = sample_name + ".consensus.fa"
            f_path = os.path.join(self.input_folder, f_name)
            try:
                record_fasta = relecov_tools.utils.read_fasta_return_SeqIO_instance(
                    f_path
                )
            except FileNotFoundError as e:
                missing_consens.append(e.filename)
                for item in mapping_fields:
                    row[item] = "Not Provided [GENEPIO:0001668]"
                continue
            row["consensus_genome_length"] = str(len(record_fasta))
            row["consensus_sequence_name"] = record_fasta.description
            row["consensus_sequence_filepath"] = self.input_folder
            row["consensus_sequence_filename"] = f_name
            row["consensus_sequence_md5"] = relecov_tools.utils.calculate_md5(f_path)
            if row["read_length"].isdigit():
                base_calculation = int(row["read_length"]) * len(record_fasta)
                if row["submitting_lab_sample_id"] != "Not Provided [GENEPIO:0001668]":
                    row["number_of_base_pairs_sequenced"] = str(base_calculation * 2)
                else:
                    row["number_of_base_pairs_sequenced"] = str(base_calculation)
            else:
                row["number_of_base_pairs_sequenced"] = "Not Provided [GENEPIO:0001668]"
            conserrs = len(missing_consens)
            if conserrs >= 1:
                log.error(
                    "{0} Consensus files missing:\n{1}".format(
                        conserrs, missing_consens
                    )
                )
                stderr.print(f"[yellow]{conserrs} samples missing consensus file:")
                stderr.print(f"[yellow]\n{missing_consens}")
        return j_data

    def parse_long_table(self, long_table_path, output_folder):
        file_match = os.path.join(long_table_path, "variants_long_table*.csv")
        table_path = glob.glob(file_match)
        if len(table_path) == 1:
            table_path = glob.glob(file_match)[0]
        else:
            log.error("variants_long_table files found = %s", len(table_path))
            stderr.print(
                f"[red]Found {len(table_path)} variants_long_table files in ",
                f"[red]{long_table_path}, aborting",
            )
            sys.exit(1)
        if not os.path.isfile(table_path):
            log.error("variants_long_table given file is not a file")
            stderr.print("[red]Variants_long_table file do not exist, Aborting")
            sys.exit(1)
        long_table = LongTableParse(table_path, output_folder)

        long_table.parsing_csv()

        return

    def include_custom_data(self, j_data):
        """Include custom fields like variant-long-table path"""
        condition = os.path.join(self.input_folder, "*variants_long_table*.csv")
        f_path = relecov_tools.utils.get_files_match_condition(condition)
        if len(f_path) == 0:
            long_table_path = "Not Provided [GENEPIO:0001668]"
        else:
            long_table_path = f_path[0]
        for row in j_data:
            row["long_table_path"] = long_table_path
        return j_data

    def include_variant_metrics(self, j_data):
        """Include the # Ns per 100kb consensus from the summary variant
        metric file_exists
        """
        map_data = relecov_tools.utils.read_csv_file_return_dict(
            self.req_files["variants_metrics"], sep=","
        )
        mapping_fields = self.configuration.get_topic_data(
            self.software_name, "mapping_variant_metrics"
        )
        j_data_with_variant_metrics = self.mapping_over_table(
            j_data, map_data, mapping_fields, "variant metrics"
        )
        return j_data_with_variant_metrics

    def include_software_versions(self, j_data):
        """Include versions from the yaml version file"""
        version_fields = self.configuration.get_topic_data(
            self.software_name, "mapping_version"
        )
        try:
            versions = relecov_tools.utils.read_yml_file(self.req_files["versions"])
        except YAMLError as e:
            log.error("Unable to process version file return error %s", e)
            stderr.print(f"[red]Unable to process version file {e}")
            sys.exit(1)
        for row in j_data:
            for field, version_data in version_fields.items():
                for key, value in version_data.items():
                    row[field] = versions[key][value]
        return j_data

    def collect_info_from_lab_json(self):
        """Create the list of dictionaries from the data that is on json lab
        metadata file. Return j_data that is used to add the rest of the fields
        """
        try:
            json_lab_data = relecov_tools.utils.read_json_file(self.json_file)
        except ValueError:
            log.error("%s invalid json file", self.json_file)
            stderr.print(f"[red] {self.json_file} invalid json file")
            sys.exit(1)
        return json_lab_data

    def create_bioinfo_file(self):
        """Create the bioinfodata json with collecting information from lab
        metadata json, mapping_stats, and more information from the files
        inside input directory
        """
        stderr.print("[blue]Reading lab metadata json")
        j_data = self.collect_info_from_lab_json()
        stderr.print("[blue]Adding fixed values")
        j_data = self.add_fixed_values(j_data, "fixed_values")
        # Creating empty fields that are not managed in case of missing data
        j_data = self.add_fixed_values(j_data, "feed_empty_fields")
        stderr.print("[blue]Adding data from mapping stats")
        j_data = self.include_data_from_mapping_stats(j_data)
        stderr.print("[blue]Adding software versions")
        j_data = self.include_software_versions(j_data)
        stderr.print("[blue]Adding summary variant metrics")
        j_data = self.include_variant_metrics(j_data)
        stderr.print("[blue]Adding pangolin information")
        j_data = self.include_pangolin_data(j_data)
        stderr.print("[blue]Adding consensus data")
        j_data = self.include_consensus_data(j_data)
        stderr.print("[blue]Parsing variants_long_table info to json format...")
        self.parse_long_table(self.input_folder, self.output_folder)
        stderr.print("[blue]Adding variant long table path")
        j_data = self.include_custom_data(j_data)
        file_name = (
            "bioinfo_" + os.path.splitext(os.path.basename(self.json_file))[0] + ".json"
        )
        stderr.print("[blue]Writting output json file")
        os.makedirs(self.output_folder, exist_ok=True)
        file_path = os.path.join(self.output_folder, file_name)
        relecov_tools.utils.write_json_fo_file(j_data, file_path)
        stderr.print("[green]Sucessful creation of bioinfo analyis file")
        return True
