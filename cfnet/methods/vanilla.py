# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/05a_methods.vanilla.ipynb.

# %% ../../nbs/05a_methods.vanilla.ipynb 3
from __future__ import annotations
from ..import_essentials import *
from .base import BaseCFModule
from ..datasets import TabularDataModule
from cfnet.utils import (
    check_cat_info,
    validate_configs,
    binary_cross_entropy,
    cat_normalize,
    grad_update,
)


# %% auto 0
__all__ = ['VanillaCFConfig', 'VanillaCF']

# %% ../../nbs/05a_methods.vanilla.ipynb 4
def _vanilla_cf(
    x: jnp.DeviceArray,  # `x` shape: (k,), where `k` is the number of features
    pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray],  # y = pred_fn(x)
    n_steps: int,
    lr: float,  # learning rate for each `cf` optimization step
    lambda_: float,  #  loss = validity_loss + lambda_params * cost
    cat_arrays: List[List[str]],
    cat_idx: int,
) -> jnp.DeviceArray:  # return `cf` shape: (k,)
    def loss_fn_1(cf_y: jnp.DeviceArray, y_prime: jnp.DeviceArray):
        return jnp.mean(binary_cross_entropy(y_pred=cf_y, y=y_prime))

    def loss_fn_2(x: jnp.DeviceArray, cf: jnp.DeviceArray):
        return jnp.mean(optax.l2_loss(cf, x))

    def loss_fn(
        cf: jnp.DeviceArray,  # `cf` shape: (k, 1)
        x: jnp.DeviceArray,  # `x` shape: (k, 1)
        pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray],
    ):
        y_pred = pred_fn(x)
        y_prime = 1.0 - y_pred
        cf_y = pred_fn(cf)
        return loss_fn_1(cf_y, y_prime) + lambda_ * loss_fn_2(x, cf)

    @jax.jit
    def gen_cf_step(
        x: jnp.DeviceArray, cf: jnp.DeviceArray, opt_state: optax.OptState
    ) -> Tuple[jnp.DeviceArray, optax.OptState]:
        cf_grads = jax.grad(loss_fn)(cf, x, pred_fn)
        cf, opt_state = grad_update(cf_grads, cf, opt_state, opt)
        cf = cat_normalize(cf, cat_arrays=cat_arrays, cat_idx=cat_idx, hard=False)
        cf = jnp.clip(cf, 0.0, 1.0)
        return cf, opt_state

    x_size = x.shape
    if len(x_size) > 1 and x_size[0] != 1:
        raise ValueError(
            f"""Invalid Input Shape: Require `x.shape` = (1, k) or (k, ),
but got `x.shape` = {x.shape}. This method expects a single input instance."""
        )
    if len(x_size) == 1:
        x = x.reshape(1, -1)
    cf = jnp.array(x, copy=True)
    opt = optax.rmsprop(lr)
    opt_state = opt.init(cf)
    for _ in tqdm(range(n_steps)):
        cf, opt_state = gen_cf_step(x, cf, opt_state)

    cf = cat_normalize(cf, cat_arrays=cat_arrays, cat_idx=cat_idx, hard=True)
    return cf.reshape(x_size)


# %% ../../nbs/05a_methods.vanilla.ipynb 5
class VanillaCFConfig(BaseParser):
    n_steps: int = 1000
    lr: float = 0.01
    lambda_: float = 0.01  # loss = validity_loss + lambda_ * cost


# %% ../../nbs/05a_methods.vanilla.ipynb 6
class VanillaCF(BaseCFModule):
    name = "VanillaCF"

    def __init__(
        self,
        configs: dict | VanillaCFConfig,
        data_module: Optional[TabularDataModule] = None,
    ):
        self.configs = validate_configs(configs, VanillaCFConfig)
        if data_module:
            self.update_cat_info(data_module)

    def generate_cf(
        self,
        x: jnp.ndarray,  # `x` shape: (k,), where `k` is the number of features
        pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray],
    ) -> jnp.DeviceArray:
        return _vanilla_cf(
            x=x,  # `x` shape: (k,), where `k` is the number of features
            pred_fn=pred_fn,  # y = pred_fn(x)
            n_steps=self.configs.n_steps,
            lr=self.configs.lr,  # learning rate for each `cf` optimization step
            lambda_=self.configs.lambda_,  #  loss = validity_loss + lambda_params * cost
            cat_arrays=self.cat_arrays,
            cat_idx=self.cat_idx,
        )

    @check_cat_info
    def generate_cfs(
        self,
        X: jnp.DeviceArray,  # `x` shape: (b, k), where `b` is batch size, `k` is the number of features
        pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray],
        is_parallel: bool = False,
    ) -> jnp.DeviceArray:
        def _generate_cf(x: jnp.DeviceArray) -> jnp.ndarray:
            return self.generate_cf(x, pred_fn)

        return (
            jax.vmap(_generate_cf)(X) if not is_parallel else jax.pmap(_generate_cf)(X)
        )

