# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/methods/01_vanilla.ipynb.

# %% ../../nbs/methods/01_vanilla.ipynb 3
from __future__ import annotations
from ..import_essentials import *
from .base import CFModule
from ..base import BaseConfig
from ..utils import auto_reshaping, grad_update, validate_configs

# %% auto 0
__all__ = ['VanillaCFConfig', 'VanillaCF']

# %% ../../nbs/methods/01_vanilla.ipynb 5
@auto_reshaping('x')
def _vanilla_cf(
    x: jnp.DeviceArray,  # `x` shape: (k,), where `k` is the number of features
    y_target: Array, # `y_target` shape: (1,)
    pred_fn: Callable[[Array], Array],  # y = pred_fn(x)
    n_steps: int,
    lr: float,  # learning rate for each `cf` optimization step
    lambda_: float,  #  loss = validity_loss + lambda_params * cost
    validity_fn: Callable,
    cost_fn: Callable,
    apply_constraints_fn: Callable
) -> jnp.DeviceArray:  # return `cf` shape: (k,)
    @jit
    def loss_fn_1(y_true: Array, y_pred: Array):
        return validity_fn(y_true, y_pred).mean()

    @jit
    def loss_fn_2(x: Array, cf: Array):
        return cost_fn(cf, x).mean()

    @partial(jit, static_argnums=(2,))
    def loss_fn(
        cf: Array,  # `cf` shape: (k, 1)
        x: Array,  # `x` shape: (k, 1)
        pred_fn: Callable[[Array], Array],
    ):
        y_pred = pred_fn(x)
        # cf_y_true = 1.0 - y_pred
        cf_y_pred = pred_fn(cf)
        return loss_fn_1(y_target, cf_y_pred) + lambda_ * loss_fn_2(x, cf)

    @loop_tqdm(n_steps)
    def gen_cf_step(
        i, cf_opt_state: Tuple[Array, optax.OptState] #x: Array, cf: Array, opt_state: optax.OptState
    ) -> Tuple[jnp.DeviceArray, optax.OptState]:
        cf, opt_state = cf_opt_state
        cf_grads = jax.grad(loss_fn)(cf, x, pred_fn)
        cf, opt_state = grad_update(cf_grads, cf, opt_state, opt)
        cf = apply_constraints_fn(x, cf, hard=False)
        return cf, opt_state

    cf = jnp.array(x, copy=True)
    opt = optax.rmsprop(lr)
    opt_state = opt.init(cf)
    cf, opt_state = lax.fori_loop(0, n_steps, gen_cf_step, (cf, opt_state))

    cf = apply_constraints_fn(x, cf, hard=True)
    return cf

# %% ../../nbs/methods/01_vanilla.ipynb 6
class VanillaCFConfig(BaseConfig):
    n_steps: int = 100
    lr: float = 0.1
    lambda_: float = 0.1
    validity_fn: str = 'KLDivergence'

# %% ../../nbs/methods/01_vanilla.ipynb 7
class VanillaCF(CFModule):

    def __init__(
        self,
        configs: dict | VanillaCFConfig = None,
        name: str = None,
    ):
        if configs is None:
            configs = VanillaCFConfig()
        configs = validate_configs(configs, VanillaCFConfig)
        name = "VanillaCF" if name is None else name
        super().__init__(configs, name=name)

    @auto_reshaping('x')
    def generate_cf(
        self,
        x: Array,  # `x` shape: (k,), where `k` is the number of features
        pred_fn: Callable[[Array], Array],
        y_target: Array = None,
        **kwargs,
    ) -> jnp.DeviceArray:
        # TODO: Currently assumes binary classification.
        if y_target is None:
            y_target = 1 - pred_fn(x)
        else:
            y_target = jnp.array(y_target, copy=True)

        return _vanilla_cf(
            x=x,  # `x` shape: (k,), where `k` is the number of features
            y_target=y_target,  # `y_target` shape: (1,)
            pred_fn=pred_fn,  # y = pred_fn(x)
            n_steps=self.config.n_steps,
            lr=self.config.lr,  # learning rate for each `cf` optimization step
            lambda_=self.config.lambda_,  #  loss = validity_loss + lambda_params * cost
            validity_fn=keras.losses.get({'class_name': self.config.validity_fn, 'config': {'reduction': None}}),
            cost_fn=keras.losses.get({'class_name': 'MeanSquaredError', 'config': {'reduction': None}}),
            apply_constraints_fn=self.apply_constraints,
        )

