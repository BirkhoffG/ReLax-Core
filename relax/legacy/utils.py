# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/legacy/00_utils.ipynb.

# %% ../../nbs/legacy/00_utils.ipynb 3
from __future__ import annotations
from .import_essentials import *
import nbdev
from fastcore.basics import AttrDict
from nbdev.showdoc import BasicMarkdownRenderer
from inspect import isclass
from fastcore.test import *
from jax.core import InconclusiveDimensionOperation

# %% auto 0
__all__ = ['validate_configs', 'cat_normalize', 'make_model', 'make_hk_module', 'init_net_opt', 'grad_update', 'check_cat_info',
           'load_json', 'binary_cross_entropy', 'sigmoid', 'accuracy', 'dist', 'proximity', 'get_config']

# %% ../../nbs/legacy/00_utils.ipynb 5
def validate_configs(
    configs: dict | BaseParser,  # A configuration of the model/dataset.
    config_cls: BaseParser,  # The desired configuration class.
) -> BaseParser:
    """return a valid configuration object."""

    assert isclass(config_cls), f"`config_cls` should be a class."
    assert issubclass(config_cls, BaseParser), \
        f"{config_cls} should be a subclass of `BaseParser`."
    
    if isinstance(configs, dict):
        configs = config_cls(**configs)
    if not isinstance(configs, config_cls):
        raise TypeError(
            f"configs should be either a `dict` or an instance of {config_cls.__name__}.")
    return configs

# %% ../../nbs/legacy/00_utils.ipynb 15
def cat_normalize(
    cf: jnp.ndarray,  # Unnormalized counterfactual explanations `[n_samples, n_features]`
    cat_arrays: List[List[str]],  # A list of a list of each categorical feature name
    cat_idx: int,  # Index that starts categorical features
    hard: bool = False,  # If `True`, return one-hot vectors; If `False`, return probability normalized via softmax
) -> jnp.ndarray:
    """Ensure generated counterfactual explanations to respect one-hot encoding constraints."""
    cf_cont = cf[:, :cat_idx]
    normalized_cf = [cf_cont]

    for col in cat_arrays:
        cat_end_idx = cat_idx + len(col)
        _cf_cat = cf[:, cat_idx:cat_end_idx]

        cf_cat = lax.cond(
            hard,
            true_fun=lambda x: jax.nn.one_hot(jnp.argmax(x, axis=-1), len(col)),
            false_fun=lambda x: jax.nn.softmax(x, axis=-1),
            operand=_cf_cat,
        )

        cat_idx = cat_end_idx
        normalized_cf.append(cf_cat)
    return jnp.concatenate(normalized_cf, axis=-1)


# %% ../../nbs/legacy/00_utils.ipynb 27
def make_model(
    m_configs: Dict[str, Any], model: hk.Module  # model configs
) -> hk.Transformed:
    # example:
    # net = make_model(PredictiveModel)
    # params = net.init(...)
    def model_fn(x, is_training: bool = True):
        return model(m_configs)(x, is_training)

    return hk.transform(model_fn)


# %% ../../nbs/legacy/00_utils.ipynb 28
def make_hk_module(
    module: hk.Module, # haiku module 
    *args, # haiku module arguments
    **kargs, # haiku module arguments
) -> hk.Transformed:

    def model_fn(x, is_training: bool = True):
        return module(*args, **kargs)(x, is_training)
    
    return hk.transform(model_fn)


# %% ../../nbs/legacy/00_utils.ipynb 29
def init_net_opt(
    net: hk.Transformed,
    opt: optax.GradientTransformation,
    X: jax.Array,
    key: random.PRNGKey,
) -> Tuple[hk.Params, optax.OptState]:
    X = device_put(X)
    params = net.init(key, X, is_training=True)
    opt_state = opt.init(params)
    return params, opt_state


# %% ../../nbs/legacy/00_utils.ipynb 30
def grad_update(
    grads: Dict[str, jnp.ndarray],
    params: hk.Params,
    opt_state: optax.OptState,
    opt: optax.GradientTransformation,
) -> Tuple[hk.Params, optax.OptState]:
    updates, opt_state = opt.update(grads, opt_state, params)
    upt_params = optax.apply_updates(params, updates)
    return upt_params, opt_state


# %% ../../nbs/legacy/00_utils.ipynb 31
def check_cat_info(method):
    def inner(cf_module, *args, **kwargs):
        warning_msg = f"""This CFExplanationModule might not be updated with categorical information.
You should try `{cf_module.name}.update_cat_info(dm)` before generating cfs.
        """
        if cf_module.cat_idx == 0 and cf_module.cat_arrays == []:
            warnings.warn(warning_msg, RuntimeWarning)
        return method(cf_module, *args, **kwargs)

    return inner


# %% ../../nbs/legacy/00_utils.ipynb 33
def load_json(f_name: str) -> Dict[str, Any]:  # file name
    with open(f_name) as f:
        return json.load(f)


# %% ../../nbs/legacy/00_utils.ipynb 35
def binary_cross_entropy(
    preds: jax.Array, # The predicted values
    labels: jax.Array # The ground-truth labels
) -> jax.Array: # Loss value
    """Per-sample binary cross-entropy loss function."""

    # Clip the predictions to avoid NaNs in the log
    preds = jnp.clip(preds, 1e-7, 1 - 1e-7)

    # Compute the binary cross-entropy
    loss = -labels * jnp.log(preds) - (1 - labels) * jnp.log(1 - preds)

    return loss

# %% ../../nbs/legacy/00_utils.ipynb 36
def sigmoid(x):
    # https://stackoverflow.com/a/68293931
    return 0.5 * (jnp.tanh(x / 2) + 1)

# %% ../../nbs/legacy/00_utils.ipynb 38
def accuracy(y_true: jnp.ndarray, y_pred: jnp.ndarray) -> jax.Array:
    y_true, y_pred = map(jnp.round, (y_true, y_pred))
    return jnp.mean(jnp.equal(y_true, y_pred))


def dist(x: jnp.ndarray, cf: jnp.ndarray, ord: int = 2) -> jax.Array:
    dist = jnp.linalg.norm(x - cf, ord=ord, axis=-1, keepdims=True)
    return jnp.mean(vmap(jnp.sum)(dist))


def proximity(x: jnp.ndarray, cf: jnp.ndarray) -> jax.Array:
    return dist(x, cf, ord=1)

# %% ../../nbs/legacy/00_utils.ipynb 41
@dataclass
class Config:
    rng_reserve_size: int
    global_seed: int

    @classmethod
    def default(cls) -> Config:
        return cls(rng_reserve_size=1, global_seed=42)

main_config = Config.default()

# %% ../../nbs/legacy/00_utils.ipynb 42
def get_config() -> Config: 
    return main_config
