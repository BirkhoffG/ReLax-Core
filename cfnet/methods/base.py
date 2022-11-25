# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/05_methods.base.ipynb.

# %% ../../nbs/05_methods.base.ipynb 3
from __future__ import annotations
from ..import_essentials import *
from ..datasets import TabularDataModule
from ..train import TrainingConfigs
from copy import deepcopy

# %% auto 0
__all__ = ['BaseCFModule', 'ParametricCFModule']

# %% ../../nbs/05_methods.base.ipynb 4
class BaseCFModule(ABC):
    cat_arrays = []
    cat_idx = 0

    @property
    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def generate_cfs(
        self,
        X: jnp.ndarray,
        pred_fn: Callable = None
    ) -> jnp.ndarray:
        pass

    def update_cat_info(self, data_module: TabularDataModule):
        # TODO: need refactor
        self.cat_arrays = deepcopy(data_module.cat_arrays)
        self.cat_idx = data_module.cat_idx
        self.imutable_idx_list = deepcopy(data_module.imutable_idx_list)


# %% ../../nbs/05_methods.base.ipynb 5
class ParametricCFModule(ABC):
    @abstractmethod
    def train(
        self, 
        datamodule: TabularDataModule, # data module
        t_configs: TrainingConfigs | dict = None # training configs; see docs in `TrainingConfigs`
    ): 
        pass

    @abstractmethod
    def _is_module_trained(self) -> bool: pass
