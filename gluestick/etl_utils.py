"""Utilities for hotglue ETL scripts."""

import hashlib
import json
import os

import pandas as pd
import pyarrow.parquet as pq


def read_csv_folder(path, converters={}, index_cols={}, ignore=[]):
    """Read a set of CSV files in a folder using read_csv().

    Notes
    -----
    This method assumes that the files are being pulled in a stream and follow a
    naming convention with the stream/ entity / table name is the first word in the
    file name for example; Account-20200811T121507.csv is for an entity called
    ``Account``.

    Parameters
    ----------
    path: str
        The folder directory
    converters: dict
        A dictionary with an array of converters that are passed to
        read_csv, the key of the dictionary is the name of the entity.
    index_cols:
        A dictionary with an array of index_cols, the key of the dictionary is the name
        of the entity.
    ignore: list
        List of files to ignore

    Returns
    -------
    return: dict
        Dict of pandas.DataFrames. the keys of which are the entity names

    Examples
    --------
    IN[31]: entity_data = read_csv_folder(
        CSV_FOLDER_PATH,
        index_cols={'Invoice': 'DocNumber'},
        converters={'Invoice': {
            'Line': ast.literal_eval,
            'CustomField': ast.literal_eval,
            'Categories': ast.literal_eval
            }}
        )
    IN[32]: df = entity_data['Account']

    """
    is_directory = os.path.isdir(path)
    all_files = []
    results = {}
    if is_directory:
        for entry in os.listdir(path):
            if os.path.isfile(os.path.join(path, entry)) and os.path.join(
                path, entry
            ).endswith(".csv"):
                all_files.append(os.path.join(path, entry))

    else:
        all_files.append(path)

    for file in all_files:
        split_path = file.split("/")
        entity_type = split_path[len(split_path) - 1].rsplit(".csv", 1)[0]

        if "-" in entity_type:
            entity_type = entity_type.rsplit("-", 1)[0]

        if entity_type not in results and entity_type not in ignore:
            # print(f"Reading file of type {entity_type} in the data file {file}")
            results[entity_type] = pd.read_csv(
                file,
                index_col=index_cols.get(entity_type),
                converters=converters.get(entity_type),
            )

    return results


def read_parquet_folder(path, ignore=[]):
    """Read a set of parquet files in a folder using read_parquet().

    Notes
    -----
    This method assumes that the files are being pulled in a stream and follow a
    naming convention with the stream/ entity / table name is the first word in the
    file name for example; Account-20200811T121507.parquet is for an entity called
    ``Account``.

    Parameters
    ----------
    path: str
        The folder directory
    ignore: list
        List of files to ignore

    Returns
    -------
    return: dict
        Dict of pandas.DataFrames. the keys of which are the entity names

    Examples
    --------
    IN[31]: entity_data = read_parquet_folder(PARQUET_FOLDER_PATH)
    IN[32]: df = entity_data['Account']

    """
    is_directory = os.path.isdir(path)
    all_files = []
    results = {}
    if is_directory:
        for entry in os.listdir(path):
            if os.path.isfile(os.path.join(path, entry)) and os.path.join(
                path, entry
            ).endswith(".parquet"):
                all_files.append(os.path.join(path, entry))

    else:
        all_files.append(path)

    for file in all_files:
        split_path = file.split("/")
        entity_type = split_path[len(split_path) - 1].rsplit(".parquet", 1)[0]

        if "-" in entity_type:
            entity_type = entity_type.rsplit("-", 1)[0]

        if entity_type not in results and entity_type not in ignore:
            results[entity_type] = pd.read_parquet(file, use_nullable_dtypes=True)

    return results


def read_snapshots(stream, snapshot_dir, **kwargs):
    """Read a snapshot file.

    Parameters
    ----------
    stream: str
        The name of the stream to extract the snapshots from.
    snapshot_dir: str
        The path for the directory where the snapshots are stored.
    **kwargs:
        Additional arguments that are passed to pandas read_csv.

    Returns
    -------
    return: pd.DataFrame
        A pandas dataframe with the snapshot data.

    """
    # Read snapshot file if it exists
    if os.path.isfile(f"{snapshot_dir}/{stream}.snapshot.csv"):
        snapshot = pd.read_csv(f"{snapshot_dir}/{stream}.snapshot.csv", **kwargs)
    else:
        snapshot = None
    return snapshot


def snapshot_records(
    stream_data, stream, snapshot_dir, pk="id", just_new=False, **kwargs
):
    """Update a snapshot file.

    Parameters
    ----------
    stream_data: str
        DataFrame with the data to be included in the snapshot.
    stream: str
        The name of the stream of the snapshots.
    snapshot_dir: str
        The name of the stream of the snapshots.
    pk: str
        The primary key used for the snapshot.
    just_new: str
        Return just the input data if True, else returns the whole data
    **kwargs:
        Additional arguments that are passed to pandas read_csv.

    Returns
    -------
    return: pd.DataFrame
        A pandas dataframe with the snapshot data.

    """
    # Read snapshot file if it exists
    snapshot = read_snapshots(stream, snapshot_dir, **kwargs)

    # If snapshot file and stream data exist update the snapshot
    if stream_data is not None and snapshot is not None:
        merged_data = pd.concat([snapshot, stream_data])
        merged_data = merged_data.drop_duplicates(pk, keep="last")
        merged_data.to_csv(f"{snapshot_dir}/{stream}.snapshot.csv", index=False)
        if not just_new:
            return merged_data

    # If there is no snapshot file snapshots and return the new data
    if stream_data is not None and snapshot is None:
        stream_data.to_csv(f"{snapshot_dir}/{stream}.snapshot.csv", index=False)
        return stream_data

    # If the new data is empty return snapshot
    if just_new:
        return stream_data
    else:
        return snapshot


def get_row_hash(row):
    """Update a snapshot file.

    Parameters
    ----------
    row: pd.DataSeries
        DataFrame row to create the hash from.

    Returns
    -------
    return: str
        A string with the hash for the row.

    """
    row_str = "".join(row.astype(str).values).encode()
    return hashlib.md5(row_str).hexdigest()


def drop_redundant(df, name, output_dir, pk=[], updated_flag=False):
    """Drop the rows that were present in previous versions of the dataframe.

    Notes
    -----
    This function will create a hash for every row of the dataframe and snapshot it, if
    the same row was present in previous versions of the dataframe, it will be dropped.

    Parameters
    ----------
    df: pd.DataFrame
        The dataframe do be checked for duplicates
    name: str
        The name used to snapshot the hash.
    output_dir: str
        The snapshot directory to save the state in.
    pk: list, str
        Primary key(s) used to associate the state with.
    updated_flag: bool
        To create of not a column with a flag for new/updated rows for the given
        primary key.

    Returns
    -------
    return: pd.DataFrame
        Dataframe with the data after dropping the redundant rows.

    """
    df = df.copy()

    if pk:
        # PK needs to be unique, so we drop the duplicated values
        df = df.drop_duplicates(subset=pk)

    df["hash"] = df.apply(get_row_hash, axis=1)
    # If there is a snapshot file compare and filter the hashs
    if os.path.isfile(f"{output_dir}/{name}.hash.snapshot.csv"):
        pk = [pk] if not isinstance(pk, list) else pk

        hash_df = pd.read_csv(f"{output_dir}/{name}.hash.snapshot.csv")

        if pk:
            hash_df = hash_df.drop_duplicates(subset=pk)

        if updated_flag and pk:
            updated_pk = df[pk]
            updated_pk["_updated"] = updated_pk.isin(hash_df[pk])

        df = df.merge(
            hash_df[pk + ["hash"]], on=pk + ["hash"], how="left", indicator=True
        )
        df = df[df["_merge"] == "left_only"]
        df = df.drop("_merge", axis=1)
        df = df.merge(updated_pk, on=pk, how="left")

    snapshot_records(df[pk + ["hash"]], f"{name}.hash", output_dir, pk)
    df = df.drop("hash", axis=1)
    return df


class Reader:
    """A reader for gluestick ETL files."""

    ROOT_DIR = os.environ.get("ROOT_DIR", ".")
    INPUT_DIR = f"{ROOT_DIR}/sync-output"

    def __init__(self, dir=INPUT_DIR, root=ROOT_DIR):
        """Init the class and read directories.

        Parameters
        ----------
        dir: str
            Directory with the input data.
        root: str
            Root directory.

        """
        self.root = root
        self.dir = dir
        self.input_files = self.read_directories()

    def __dict__(self):
        return self.input_files

    def __str__(self):
        return str(list(self.input_files.keys()))

    def __repr__(self):
        return str(list(self.input_files.keys()))

    def get(self, stream, default=None, catalog_types=False, **kwargs):
        """Read the selected file."""
        filepath = self.input_files.get(stream)
        if not filepath:
            return default
        if filepath.endswith(".parquet"):
            return pd.read_parquet(filepath, use_nullable_dtypes=True, **kwargs)
        catalog = self.read_catalog()
        if catalog and catalog_types:
            types_params = self.get_types_from_catalog(catalog, stream)
            kwargs.update(types_params)
        return pd.read_csv(filepath, **kwargs)

    def get_metadata(self, stream):
        """Get metadata from parquet file."""
        file = self.input_files.get(stream)
        if file.endswith(".parquet"):
            return {
                k.decode(): v.decode()
                for k, v in pq.read_metadata(file).metadata.items()
            }
        return {}

    def read_directories(self, ignore=[]):
        """Read all the available directories for input files.

        Parameters
        ----------
        ignore: list
            Stream names to ignore.

        Returns
        -------
        return: dict
            Dict with the name of the streams and their paths.

        """
        is_directory = os.path.isdir(self.dir)
        all_files = []
        results = {}
        if is_directory:
            for entry in os.listdir(self.dir):
                file_path = os.path.join(self.dir, entry)
                if os.path.isfile(file_path):
                    if file_path.endswith(".csv") or file_path.endswith(".parquet"):
                        all_files.append(file_path)
        else:
            all_files.append(self.dir)

        for file in all_files:
            split_path = file.split("/")
            entity_type = split_path[len(split_path) - 1].rsplit(".", 1)[0]

            if "-" in entity_type:
                entity_type = entity_type.rsplit("-", 1)[0]

            if entity_type not in results and entity_type not in ignore:
                results[entity_type] = file

        return results

    def read_catalog(self):
        """Read the catalog.json file."""
        filen_name = f"{self.root}/catalog.json"
        if os.path.isfile(filen_name):
            with open(filen_name) as f:
                catalog = json.load(f)
        else:
            catalog = None
        return catalog

    def get_types_from_catalog(self, catalog, stream):
        """Get the pandas types base on the catalog definition.

        Parameters
        ----------
        catalog: dict
            The singer catalog used on the tap.
        stream: str
            The name of the stream.

        Returns
        -------
        return: dict
            Dict with arguments to be used by pandas.

        """
        filepath = self.input_files.get(stream)
        headers = pd.read_csv(filepath, index_col=0, nrows=0).columns.tolist()

        streams = next(c for c in catalog["streams"] if c["stream"] == stream)
        types = streams["schema"]["properties"]

        type_mapper = {"integer": "Int64", "number": float}

        dtype = {}
        parse_dates = []
        for col in headers:
            col_type = types.get(col)
            if col_type:
                if col_type.get("format") == "date-time":
                    parse_dates.append(col)
                    continue
                if col_type.get("type"):
                    catalog_type = [t for t in col_type["type"] if t != "null"]
                    if len(catalog_type) == 1:
                        dtype[col] = type_mapper.get(catalog_type[0], "object")
                        continue
            dtype[col] = "object"

        return dict(dtype=dtype, parse_dates=parse_dates)
