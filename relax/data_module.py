# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_data.ipynb.

# %% ../nbs/01_data.ipynb 3
from __future__ import annotations
from .utils import load_json, validate_configs, get_config, save_pytree, load_pytree
from .base import *
from .data_utils import *
import jax
from jax import numpy as jnp, random as jrand, lax, Array
import pandas as pd
import numpy as np
from pathlib import Path
import json, os, shutil
from urllib.request import urlretrieve
from pydantic.fields import ModelField, Field
from typing import List, Dict, Union, Optional, Tuple, Callable, Any, Iterable

# %% auto 0
__all__ = ['BaseDataModule', 'DataModuleConfig', 'DataModule', 'download_data_module_files', 'load_data']

# %% ../nbs/01_data.ipynb 6
class BaseDataModule(BaseModule):
    """DataModule Interface"""

    def prepare(self, *args, **kwargs):
        """Prepare data for training"""
        raise NotImplementedError
        
    def apply_constraints(self, x: Array, cf: Array, hard: bool = False, **kwargs) -> Array:
        raise NotImplementedError
    
    def compute_reg_loss(self, x: Array, cf: Array, hard: bool = False, **kwargs) -> float:
        raise NotImplementedError

# %% ../nbs/01_data.ipynb 8
class DataModuleConfig(BaseConfig):
    """Configurator of `TabularDataModule`."""

    data_dir: str = Field(description="The directory of dataset.")
    data_name: str = Field(description="The name of `DataModule`.")
    continous_cols: List[str] = Field([], description="Continuous features/columns in the data.")
    discret_cols: List[str] = Field([], description="Categorical features/columns in the data.")
    imutable_cols: List[str] = Field([], description="Immutable features/columns in the data.")
    continuous_transformation: str = Field('minmax', description="Transformation for continuous features.")
    discret_transformation: str = Field('ohe', description="Transformation for categorical features.")
    sample_frac: Optional[float] = Field(
        None, description="Sample fraction of the data. Default to use the entire data.", ge=0., le=1.0
    )
    train_indices: List[int] = Field([], description="Indices of training data.")
    test_indices: List[int] = Field([], description="Indices of testing data.")
    
    # normalizer: Optional[str] = Field(
    #     default_factory=lambda: MinMaxScaler(),
    #     description="Sklearn scalar for continuous features. Can be unfitted, fitted, or None. "
    #     "If not fitted, the `TabularDataModule` will fit using the training data. If fitted, no fitting will be applied. "
    #     "If `None`, no transformation will be applied. Default to `MinMaxScaler()`."
    # )
    # encoder: Optional[str] = Field(
    #     default_factory=lambda: OneHotEncoder(sparse=False),
    #     description="Fitted encoder for categorical features. Can be unfitted, fitted, or None. "
    #     "If not fitted, the `TabularDataModule` will fit using the training data. If fitted, no fitting will be applied. "
    #     "If `None`, no transformation will be applied. Default to `OneHotEncoder(sparse=False)`."
    # )

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

# %% ../nbs/01_data.ipynb 10
class DataModule(BaseDataModule):
    def __init__(
        self, 
        config: Dict | DataModuleConfig, 
        data: pd.DataFrame = None,
        features: List[Feature] = None,
        label: Feature = None,
    ):
        config = validate_configs(config, DataModuleConfig)
        if data is None:
            data = pd.read_csv(config.data_dir)
        self._data = data
        features = self.convert_to_features(config, data, features)
        label = self.convert_to_label(config, data, label)
        self.prepare(features, label)
        config.shuffle(self.xs, test_size=0.25)
        super().__init__(config, name=config.data_name)
    
    def save(self, path):
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
    def load_from_path(cls, path, config=None):
        path = Path(path)
        if config is None:
            config = load_json(path / 'config.json')
        features = FeaturesList.load_from_path(path / 'features')
        label = FeaturesList.load_from_path(path / 'label')
        data = pd.read_csv(path / 'data.csv')
        return cls(config, data=data, features=features, label=label)

    def convert_to_features(
        self, 
        config: DataModuleConfig, 
        data: pd.DataFrame, 
        features: list[Feature] = None
    ):
        to_feature = lambda col, data, is_continuous: Feature(
            name=col, data=data[col].to_numpy().reshape(-1, 1),
            transformation=config.continuous_transformation if is_continuous else config.discret_transformation,
            is_immutable=col in config.imutable_cols
        )

        if features is not None:
            return features
        
        cont_features = [to_feature(col, data, True) for col in config.continous_cols]
        cat_features = [to_feature(col, data, False) for col in config.discret_cols]
        return cont_features + cat_features        
        
    def convert_to_label(self, config: DataModuleConfig, data: pd.DataFrame, label: Feature = None):
        if label is not None:
            return label
        
        label_col = data.columns[-1]
        return Feature(
            name=label_col, data=data[label_col].to_numpy().reshape(-1, 1),
            transformation='identity',
            is_immutable=label_col in config.imutable_cols
        )
        
    def prepare(self, features, label):
        if features is not None and label is not None:
            self._features = FeaturesList(features)
            self._label = FeaturesList(label)
        elif features is None:
            raise ValueError("Features cannot be None.")
        elif label is None:
            raise ValueError("Label cannot be None.")
    
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
    
    def sample(self, size: float | int, stage: str = 'train', key: jrand.PRNGKey = None):
        key = jrand.PRNGKey(0) if key is None else key
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

    def transform(self, data: pd.DataFrame):
        if isinstance(data, pd.DataFrame):
            data_dict = {k: np.array(v).reshape(-1, 1) for k, v in data.iloc[:, :-1].to_dict(orient='list').items()}
            return self._features.transform(data_dict)
        else:
            raise ValueError("data should be a pandas DataFrame.")
        
    def inverse_transform(self, data: Array):
        return self._label.inverse_transform(data)
        
    def apply_constraints(self, xs: Array, cfs: Array, hard: bool = False) -> Array:
        return self._features.apply_constraints(xs, cfs, hard)
    
    def compute_reg_loss(self, xs: Array, cfs: Array, hard: bool = False) -> float:
        return self._features.compute_reg_loss(xs, cfs, hard)

# %% ../nbs/01_data.ipynb 13
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

# %% ../nbs/01_data.ipynb 18
def _validate_dataname(data_name: str):
    if data_name not in DEFAULT_DATA:
        raise ValueError(f'`data_name` must be one of {DEFAULT_DATA}, '
            f'but got data_name={data_name}.')

# %% ../nbs/01_data.ipynb 19
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
    return_config: bool = False, # Return `data_config `or not
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

    # read config
    conf_path = data_parent_dir / f'{data_name}/data/config.json'
    config = load_json(conf_path)

    if not (data_configs is None):
        config.update(data_configs)

    config = DataModuleConfig(**config)
    data_dir = data_parent_dir / f'{data_name}/data'
    data_module = DataModule.load_from_path(data_dir, config=config)

    if return_config:
        return data_module, config
    else:
        return data_module

