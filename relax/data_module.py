# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_data.ipynb.

# %% ../nbs/01_data.ipynb 3
from __future__ import annotations
from .utils import load_json, validate_configs, get_config, save_pytree, load_pytree, get_config
from .base import *
from .data_utils import *
from .import_essentials import *
import jax
from jax import numpy as jnp, random as jrand, lax, Array
import pandas as pd
import numpy as np
from pathlib import Path
import json, os, shutil
from urllib.request import urlretrieve
from pydantic.fields import ModelField, Field
from typing import List, Dict, Union, Optional, Tuple, Callable, Any, Iterable
import warnings
from pandas.testing import assert_frame_equal

# %% auto 0
__all__ = ['BaseDataModule', 'DataModuleConfig', 'features2config', 'features2pandas', 'dataframe2features', 'dataframe2labels',
           'DataModule', 'TabularDataModuleConfigs', 'TabularDataModule', 'download_data_module_files', 'load_data']

# %% ../nbs/01_data.ipynb 6
class BaseDataModule(BaseModule):
    """DataModule Interface"""

    def _prepare(self, *args, **kwargs):
        """Prepare data for training"""
        raise NotImplementedError
        
    def apply_constraints(self, x: Array, cf: Array, hard: bool = False, **kwargs) -> Array:
        raise NotImplementedError
    
    def compute_reg_loss(self, x: Array, cf: Array, hard: bool = False, **kwargs) -> float:
        raise NotImplementedError

# %% ../nbs/01_data.ipynb 7
class DataModuleInfoMixin:
    """This base class exposes some attributes of DataModule
    at the base level for easy access.
    """

    @property
    def data(self) -> pd.DataFrame:
        return self._data
    
    @property
    def xs(self) -> Array:
        return self._features.transformed_data
    
    @property
    def ys(self) -> Array:
        return self._label.transformed_data
    
    @property
    def features(self) -> FeaturesList:
        return self._features
    
    @property
    def label(self) -> FeaturesList:
        return self._label

    @property
    def dataset(self) -> Tuple[Array, Array]:
        return (self.xs, self.ys)
    
    @property
    def train_indices(self) -> List[int]:
        return self.config.train_indices
    
    @property
    def test_indices(self) -> List[int]:
        return self.config.test_indices


# %% ../nbs/01_data.ipynb 10
class DataModuleConfig(BaseConfig):
    """Configurator of `DataModule`."""

    data_dir: str = Field(None, description="The directory of dataset.")
    data_name: str = Field(None, description="The name of `DataModule`.")
    continous_cols: List[str] = Field([], description="Continuous features/columns in the data.")
    discret_cols: List[str] = Field([], description="Categorical features/columns in the data.")
    imutable_cols: List[str] = Field([], description="Immutable features/columns in the data.")
    continuous_transformation: Optional[str] = Field('minmax', description="Transformation for continuous features. `None` indicates unknown.")
    discret_transformation: Optional[str] = Field('ohe', description="Transformation for categorical features. `None` indicates unknown.")
    sample_frac: Optional[float] = Field(
        None, description="Sample fraction of the data. Default to use the entire data.", ge=0., le=1.0
    )
    train_indices: List[int] = Field([], description="Indices of training data.")
    test_indices: List[int] = Field([], description="Indices of testing data.")
    
    def shuffle(self, data: Array, test_size: float, seed: int = None):
        """Shuffle data with a seed."""
        if seed is None:
            seed = get_config().global_seed
        key = jrand.PRNGKey(seed)
        total_length = data.shape[0]
        train_length = int((1 - test_size) * total_length)
        if len(self.train_indices) == 0:
            self.train_indices = jrand.permutation(key, total_length)[:train_length].tolist()
        if len(self.test_indices) == 0:
            self.test_indices = jrand.permutation(key, total_length)[train_length:].tolist()

# %% ../nbs/01_data.ipynb 13
def features2config(
    features: FeaturesList, # FeaturesList to be converted
    name: str, # Name of the data used for `DataModuleConfig`
    return_dict: bool = False # Whether to return a dict or `DataModuleConfig`
) -> Union[DataModuleConfig, Dict]: # Return configs
    """Get `DataModuleConfig` from `FeaturesList`."""

    cont, cats, immu = [], [], []
    cont_transformation, cat_transformation = None, None
    for f in features:
        if f.is_categorical:
            cats.append(f.name)
        else:
            cont.append(f.name)
        if f.is_immutable:
            immu.append(f.name)
    
    configs_dict = {
        "data_dir": ".",
        "data_name": name,
        "continous_cols": cont,
        "discret_cols": cats,
        "imutable_cols": immu,
        "continuous_transformation": cont_transformation,
        "discret_transformation": cat_transformation,
    }
    if return_dict:
        return configs_dict
    return DataModuleConfig(**configs_dict)


# %% ../nbs/01_data.ipynb 15
def features2pandas(
    features: FeaturesList, # FeaturesList to be converted
    labels: FeaturesList # labels to be converted
) -> pd.DataFrame: # Return pandas dataframe
    """Convert `FeaturesList` to pandas dataframe."""
    
    feats_df = features.to_pandas()
    labels_df = labels.to_pandas()
    df = pd.concat([feats_df, labels_df], axis=1)
    return df

# %% ../nbs/01_data.ipynb 18
def to_feature(col: str, data: pd.DataFrame, config: DataModuleConfig, transformation: str):
    return Feature(
        name=col, data=data[col].to_numpy().reshape(-1, 1),
        transformation=transformation,
        is_immutable=col in config.imutable_cols
    )

# %% ../nbs/01_data.ipynb 19
def dataframe2features(
    data: pd.DataFrame,
    config: DataModuleConfig,
) -> FeaturesList:
    """Convert pandas dataframe of features to `FeaturesList`."""

    cont_features = [to_feature(col, data, config, config.continuous_transformation) for col in config.continous_cols]
    cat_features = [to_feature(col, data, config, config.discret_transformation) for col in config.discret_cols]
    features = cont_features + cat_features
    return FeaturesList(features)


def dataframe2labels(
    data: pd.DataFrame,
    config: DataModuleConfig,
) -> FeaturesList:
    """Convert pandas dataframe of labels to `FeaturesList`."""
    
    label_cols = set(data.columns) - set(config.continous_cols) - set(config.discret_cols)
    labels = [to_feature(col, data, config, 'identity') for col in label_cols]
    return FeaturesList(labels)

# %% ../nbs/01_data.ipynb 21
class DataModule(BaseDataModule, DataModuleInfoMixin):
    """DataModule for tabular data."""

    def __init__(
        self, 
        features: FeaturesList,
        label: FeaturesList,
        config: DataModuleConfig = None,
        data: pd.DataFrame = None,
        **kwargs
    ):
        self._prepare(features, label)
        if config is None:
            name = kwargs.pop('name', 'DataModule')
            config = features2config(features, name)
        config.shuffle(self.xs, test_size=0.25)
        self._data = features2pandas(features, label) if data is None else data
        super().__init__(config, name=config.data_name)

    def _prepare(self, features, label):
        if features is not None and label is not None:
            self._features = FeaturesList(features)
            self._label = FeaturesList(label)
        elif features is None:
            raise ValueError("Features cannot be None.")
        elif label is None:
            raise ValueError("Label cannot be None.")
            
    def save(
        self, 
        path: str # Path to the directory to save `DataModule`
    ):
        """Save `DataModule` to a directory."""
        path = Path(path)
        if not path.exists():
            path.mkdir(parents=True)
        self._features.save(path / 'features')
        self._label.save(path / 'label')
        if self._data is not None:
            self._data.to_csv(path / 'data.csv', index=False)
        with open(path / "config.json", "w") as f:
            json.dump(self.config.dict(), f)

    @classmethod
    def load_from_path(
        cls, 
        path: str,  # Path to the directory to load `DataModule`
        config: Dict|DataModuleConfig = None # Configs of `DataModule`. This argument is ignored.
    ) -> DataModule: # Initialized `DataModule` from path
        """Load `DataModule` from a directory."""
        if config is not None:
            warnings.warn("Passing `config` will have no effect.")
        
        path = Path(path)
        config = DataModuleConfig.load_from_json(path / 'config.json')
        # config = validate_configs(config, DataModuleConfig)
        features = FeaturesList.load_from_path(path / 'features')
        label = FeaturesList.load_from_path(path / 'label')
        data = pd.read_csv(path / 'data.csv')
        return cls(features=features, label=label, config=config, data=data)
    
    @classmethod
    def from_path(cls, path, config: DataModuleConfig = None):
        """Alias of `load_from_path`"""
        return cls.load_from_path(path, config)
    
    @classmethod
    def from_config(
        cls, 
        config: Dict|DataModuleConfig, # Configs of `DataModule`
        data: pd.DataFrame=None # Passed in pd.Dataframe
    ) -> DataModule: # Initialized `DataModule` from configs and data
        config = validate_configs(config, DataModuleConfig)
        if data is None:
            data = pd.read_csv(config.data_dir)
        if not isinstance(data, pd.DataFrame):
            raise ValueError("`data` should be a pandas DataFrame.")
        features = dataframe2features(data, config)
        label = dataframe2labels(data, config)
        return cls(features=features, label=label, config=config, data=data)
    
    @classmethod
    def from_numpy(
        cls,
        xs: np.ndarray, # Input data
        ys: np.ndarray, # Labels
        name: str = None, # Name of `DataModule`
        transformation='minmax'
    ) -> DataModule: # Initialized `DataModule` from numpy arrays
        """Create `DataModule` from numpy arrays. Note that the `xs` are treated as continuous features."""
        
        features = FeaturesList([Feature(f"feature_{i}", xs[:, i].reshape(-1, 1), transformation=transformation) for i in range(xs.shape[1])])
        labels = FeaturesList([Feature(f"label", ys.reshape(-1, 1), transformation='identity')])
        return cls(features=features, label=labels, name=name)
    
    @classmethod
    def from_features(
        cls, 
        features: FeaturesList, # Features of `DataModule`
        label: FeaturesList, # Labels of `DataModule`
        name: str = None # Name of `DataModule`
    ) -> DataModule: # Initialized `DataModule` from features and labels
        """Create `DataModule` from `FeaturesList`."""
        return cls(features=features, label=label, name=name)
        
    def _get_data(self, indices):
        if isinstance(indices, list):
            indices = jnp.array(indices)
        return (self.xs[indices], self.ys[indices])
        
    def __getitem__(self, name: str):
        if name == 'train':
            return self._get_data(self.config.train_indices)
        elif name in ['valid', 'test']:
            return self._get_data(self.config.test_indices)
        else:
            raise ValueError(f"Unknown data name: {name}. Should be one of ['train', 'valid', 'test']")
    
    def set_transformations(
        self, 
        feature_names_to_transformation: Dict[str, Union[str, Dict, Transformation]], # Dict[feature_name, Transformation]
    ) -> DataModule:
        """Reset transformations for features."""

        self._features = self._features.set_transformations(feature_names_to_transformation)
        return self
    
    def sample(
        self, 
        size: float | int, # Size of the sample. If float, should be 0<=size<=1.
        stage: str = 'train', # Stage of data to sample from. Should be one of ['train', 'valid', 'test']
        key: jrand.PRNGKey = None # Random key. 
    ) -> Tuple[Array, Array]: # Sampled data
        """Sample data from `DataModule`."""

        key = jrand.PRNGKey(get_config().global_seed) if key is None else key
        xs, ys = self[stage]
        indices = jnp.arange(xs.shape[0])
        
        if isinstance(size, float) and 0 <= size <= 1:
            size = int(size * indices.shape[0])
        elif isinstance(size, int):
            size = min(size, indices.shape[0])
        else:
            raise ValueError(f"`size` should be a floating number 0<=size<=1, or an integer,"
                             f" but got size={size}.")
                
        indices = jrand.permutation(key, indices)[:size]
        return xs[indices], ys[indices]

    def transform(
        self, 
        data: pd.DataFrame | Dict[str, Array] # Data to be transformed
    ) -> Array: # Transformed data
        """Transform data to `jax.Array`."""
        # TODO: test this function
        if isinstance(data, pd.DataFrame):
            data_dict = {k: np.array(v).reshape(-1, 1) for k, v in data.iloc[:, :-1].to_dict(orient='list').items()}
            return self._features.transform(data_dict)
        elif isinstance(data, dict):
            data = jax.tree_util.tree_map(lambda x: np.array(x).reshape(-1, 1), data)
            return self._features.transform(data)
        else:
            raise ValueError("data should be a pandas DataFrame or `Dict[str, jax.Array]`.")
        
    def inverse_transform(
        self, 
        data: Array, # Data to be inverse transformed
        return_type: str = 'pandas' # Type of the returned data. Should be one of ['pandas', 'dict']
    ) -> pd.DataFrame: # Inverse transformed data
        """Inverse transform data to `pandas.DataFrame`."""
        # TODO: test this function
        inversed = self._features.inverse_transform(data)
        if return_type == 'pandas':
            return inversed
        elif return_type == 'dict':
            raise NotImplementedError
        else:
            raise ValueError(f"Unknown return type: {return_type}. Should be one of ['pandas', 'dict']")
        
    def apply_constraints(
        self, 
        xs: Array, # Input data
        cfs: Array, # Counterfactuals to be constrained
        hard: bool = False, # Whether to apply hard constraints or not
        rng_key: jrand.PRNGKey = None, # Random key
        **kwargs
    ) -> Array: # Constrained counterfactuals
        """Apply constraints to counterfactuals."""
        return self._features.apply_constraints(xs, cfs, hard=hard, rng_key=rng_key, **kwargs)
    
    def compute_reg_loss(
        self, 
        xs: Array, # Input data
        cfs: Array, # Counterfactuals to be constrained
        hard: bool = False # Whether to apply hard constraints or not
    ) -> float:
        """Compute regularization loss."""
        return self._features.compute_reg_loss(xs, cfs, hard)
    
    __ALL__ = [
        'load_from_path', 
        'from_config', 
        'from_features',
        'from_numpy',
        'save',
        'transform',
        'inverse_transform',
        'apply_constraints',
        'compute_reg_loss',
        'set_transformations',
        'sample'
    ]

# %% ../nbs/01_data.ipynb 22
def dm_equals(dm1: DataModule, dm2: DataModule):
    # data_equals = np.allclose(dm1.data.to_numpy(), dm2.data.to_numpy())
    assert_frame_equal(dm1.data, dm2.data)
    xs_equals = np.allclose(dm1.xs, dm2.xs)
    ys_equals = np.allclose(dm1.ys, dm2.ys)
    train_indices_equals = np.array_equal(dm1.train_indices, dm2.train_indices)
    test_indices_equals = np.array_equal(dm1.test_indices, dm2.test_indices)
    # print(f"data_equals: {data_equals}, xs_equals: {xs_equals}, ys_equals: {ys_equals}, train_indices_equals: {train_indices_equals}, test_indices_equals: {test_indices_equals}")
    return (
        xs_equals and ys_equals and 
        train_indices_equals and test_indices_equals
    )

# %% ../nbs/01_data.ipynb 30
class TabularDataModuleConfigs(DataModuleConfig):
    """!!!Deprecated!!! - Configurator of `TabularDataModule`."""
    def __ini__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        warnings.warn("TabularDataModuleConfigs is deprecated since v0.2, please use DataModuleConfig instead.", 
                      DeprecationWarning)

# %% ../nbs/01_data.ipynb 31
class TabularDataModule(DataModule):
    """!!!Deprecated!!! - DataModule for tabular data."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        warnings.warn("TabularDataModule is deprecated since v0.2, please use DataModule instead.", 
                      DeprecationWarning)
        
    __ALL__ = []

# %% ../nbs/01_data.ipynb 33
DEFAULT_DATA = [
    'adult',
    'heloc',
    'oulad',
    'credit',
    'cancer',
    'student_performance',
    'titanic',
    'german',
    'spam',
    'ozone',
    'qsar',
    'bioresponse',
    'churn',
    'road',
    'dummy'
 ]

DEFAULT_DATA_CONFIGS = { 
    data: { 
        'data': f"{data}/data", 'model': f"{data}/model",
    } for data in DEFAULT_DATA
}

# %% ../nbs/01_data.ipynb 38
def _validate_dataname(data_name: str):
    if data_name not in DEFAULT_DATA:
        raise ValueError(f'`data_name` must be one of {DEFAULT_DATA}, '
            f'but got data_name={data_name}.')

# %% ../nbs/01_data.ipynb 39
def download_data_module_files(
    data_name: str, # The name of data
    data_parent_dir: Path, # The directory to save data.
    download_original_data: bool = False, # Download original data or not
):
    files = [
        "features/data.npy", "features/treedef.json",
        "label/data.npy", "label/treedef.json",
        "config.json"
    ]
    if download_original_data:
        files.append("data.csv")
    for f in files:
        url = f"https://huggingface.co/datasets/birkhoffg/ReLax-Assets/resolve/main/{data_name}/data/{f}"
        f_path = data_parent_dir / f'{data_name}/data' / f
        os.makedirs(f_path.parent, exist_ok=True)
        if not f_path.is_file(): urlretrieve(url, f_path)


def load_data(
    data_name: str, # The name of data
    return_config: bool = False, # Deprecated
    data_configs: dict = None, # Data configs to override default configuration
) -> DataModule | Tuple[DataModule, DataModuleConfig]: # Return `DataModule` or (`DataModule`, `DataModuleConfig`)
    """High-level util function for loading `data` and `data_config`."""
    
    _validate_dataname(data_name)

    # create new dir
    data_parent_dir = Path(os.getcwd()) / "relax-assets"
    if not data_parent_dir.exists():
        os.makedirs(data_parent_dir, exist_ok=True)
    # download files
    download_data_module_files(
        data_name, data_parent_dir, 
        download_original_data=True
    )

    if return_config:
        warnings.warn("`return_config` is deprecated since v0.2. "
                      "Please access `config` from `DataModule`.", DeprecationWarning)

    # read and override config
    # comment them for now since we cannot garantee the override configs are valid
    # conf_path = data_parent_dir / f'{data_name}/data/config.json'
    # config = load_json(conf_path)
    # if not (data_configs is None):
    #     config.update(data_configs)
    # config = DataModuleConfig(**config)

    data_dir = data_parent_dir / f'{data_name}/data'
    data_module = DataModule.load_from_path(data_dir, config=data_configs)

    return data_module

