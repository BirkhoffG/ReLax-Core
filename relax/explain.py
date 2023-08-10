# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/03_explain.ipynb.

# %% ../nbs/03_explain.ipynb 2
from __future__ import annotations
from .import_essentials import *
from .data_module import DataModule, load_data
from .base import *
from .methods import *
from .strategy import *
from .ml_model import *
import einops
from sklearn.datasets import make_classification

# %% auto 0
__all__ = ['Explanation', 'fake_explanation', 'prepare_pred_fn', 'prepare_cf_module', 'generate_cf_explanations']

# %% ../nbs/03_explain.ipynb 4
class Explanation:
    """Generated CF Explanations class. It behaves like a `DataModule`, except a few more attributes."""

    def __init__(
        self,
        data: DataModule,  # Data module
        cfs: Array,  # Generated cf explanation of `xs` in `data`
        pred_fn: Callable[[Array], Array],  # Predict function
        total_time: float = None,  # Total runtime
        cf_name: str = "CFModule",  # CF method's name
    ):
        self._data = data
        self._cfs = cfs
        self.pred_fn = pred_fn
        self.total_time = total_time
        self.cf_name = cf_name

    def __repr__(self):
        return f"Explanation(data_name={self.data_name}, cf_name={self.cf_name}, " \
               f"total_time={self.total_time}, xs={self.xs}, ys={self.ys}, cfs={self.cfs})"

    @property
    def data(self):
        return self._data

    @property
    def xs(self):
        return self.data.xs
    
    @property
    def ys(self):
        return self.data.ys
    
    @property
    def cfs(self):
        # assert self.xs.shape == self._cfs.shape
        return self._cfs
    
    @property
    def data_name(self):
        return self.data.name

    @property
    def train_indices(self):
        return self.data.train_indices
    
    @property
    def test_indices(self):
        return self.data.test_indices
    
    def apply_constraints(self, *args, **kwargs):
        return self.data.apply_constraints(*args, **kwargs)
    
    def compute_reg_loss(self, *args, **kwargs):
        return self.data.compute_reg_loss(*args, **kwargs)

# %% ../nbs/03_explain.ipynb 5
def fake_explanation(n_cfs: int=1):
    dm = load_data('dummy')
    ml_model = load_ml_module('dummy')
    if n_cfs < 1: 
        raise ValueError(f'n_cfs must be greater than 0, but got n_cfs={n_cfs}.')
    elif n_cfs == 1:
        cfs = dm.xs
    else:
        # Allow for multiple counterfactuals
        cfs = einops.repeat(dm.xs, "n k -> n c k", c=n_cfs)

    return Explanation(
        data=dm, cfs=cfs, pred_fn=ml_model.pred_fn, total_time=0.0, cf_name='dummy_method'
    )

# %% ../nbs/03_explain.ipynb 8
def prepare_pred_fn(
    cf_module: CFModule,
    data: DataModule,
    pred_fn: Callable[[Array, ...], Array], # Predictive function. 
    pred_fn_args: Dict = None,
) -> Callable[[Array], Array]: # Return predictive function with signature `(x: Array) -> Array`.
    """Prepare the predictive function for the CF module. 
    We will train the model if `pred_fn` is not provided and `cf_module` does not have `pred_fn`.
    If `pred_fn` is found in `cf_module`, we will use it irrespective of `pred_fn` argument.
    If `pred_fn` is provided, we will use it.
    """
    # Train the model if `pred_fn` is not provided.
    if not hasattr(cf_module, 'pred_fn') and pred_fn is None:
        model = MLModule().train(data)
        return model.pred_fn
    # If `pred_fn` is detected in cf_module, 
    # use it irrespective of `pred_fn` argument.
    elif hasattr(cf_module, 'pred_fn'):
        return cf_module.pred_fn
    # If `pred_fn` is provided, use it.
    else:
        if pred_fn_args is not None:
            pred_fn = ft.partial(pred_fn, **pred_fn_args)
        return pred_fn

def prepare_cf_module(
    cf_module: CFModule,
    data_module: DataModule,
    pred_fn: Callable[[Array], Array] = None,
    train_config: Dict[str, Any] = None, 
):
    """Prepare the CF module. 
    It will hook up the data module's apply functions via the `init_apply_fns` method
    (e.g., `apply_constraints_fn` and `compute_reg_loss_fn`).
    It will also train the model if `cf_module` is a `ParametricCFModule`.
    """
    cf_module.init_fns(
        apply_constraints_fn=data_module.apply_constraints,
        compute_reg_loss_fn=data_module.compute_reg_loss,
    )
    if isinstance(cf_module, ParametricCFModule):
        cf_module.train(data_module, pred_fn=pred_fn, **train_config)
    return cf_module


# %% ../nbs/03_explain.ipynb 9
def generate_cf_explanations(
    cf_module: CFModule, # CF Explanation Module
    data: DataModule, # Data Module
    pred_fn: Callable[[Array, ...], Array] = None, # Predictive function
    strategy: str | BaseStrategy = None, # Parallelism Strategy for generating CFs. Default to `vmap`.
    train_config: Dict[str, Any] = None, 
    pred_fn_args: dict = None # auxiliary arguments for `pred_fn` 
) -> Explanation: # Return counterfactual explanations.
    """Generate CF explanations."""

    # Prepare `pred_fn`, `cf_module`, and `strategy`.
    pred_fn = prepare_pred_fn(cf_module, data, pred_fn, pred_fn_args)
    cf_module = prepare_cf_module(cf_module, data, train_config)
    if strategy is None:
        strategy = StrategyFactory.get_default_strategy()
    strategy = StrategyFactory.get_strategy(strategy)
    
    # Generate CF explanations.
    start_time = time.time()
    cfs = strategy(cf_module.generate_cf, data.xs, pred_fn).block_until_ready()
    total_time = time.time() - start_time

    # Return CF explanations.
    return Explanation(
        cf_name=cf_module.name,
        data=data,
        cfs=cfs,
        total_time=total_time,
        pred_fn=pred_fn,
    )
