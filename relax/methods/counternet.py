# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/methods/04_counternet.ipynb.

# %% ../../nbs/methods/04_counternet.ipynb 3
from __future__ import annotations
from ..import_essentials import *
from .base import CFModule, ParametricCFModule
from ..base import BaseConfig, PredFnMixedin
from ..utils import auto_reshaping, grad_update, validate_configs
from ..data_utils import Feature, FeaturesList
from ..data_module import DataModule
from ..evaluate import compute_proximity, PredictiveAccuracy
from .base import ParametricCFModule
# Legacy code for making haiku works
import haiku as hk
from ..legacy.utils import make_hk_module, init_net_opt
from ..legacy.module import MLP, BaseTrainingModule
from ..legacy.trainer import train_model

# %% auto 0
__all__ = ['CounterNetModel', 'partition_trainable_params', 'CounterNetTrainingModule', 'CounterNetConfig', 'CounterNet']

# %% ../../nbs/methods/04_counternet.ipynb 5
class CounterNetModel(hk.Module):
    """CounterNet Model"""
    def __init__(
        self,
        enc_sizes: list,
        dec_sizes: list,
        exp_sizes: list,
        dropout_rate: float,
        name: str = None,  # Name of the module.
    ):
        """CounterNet model architecture."""
        super().__init__(name=name)
        self.enc_sizes = enc_sizes
        self.dec_sizes = dec_sizes
        self.exp_sizes = exp_sizes
        self.dropout_rate = dropout_rate

    def __call__(self, x: jnp.ndarray, is_training: bool = True) -> jnp.ndarray:
        input_shape = x.shape[-1]
        # encoder
        z = MLP(self.enc_sizes, self.dropout_rate, name="Encoder")(
            x, is_training
        )

        # prediction
        pred = MLP(self.dec_sizes, self.dropout_rate, name="Predictor")(
            z, is_training
        )
        y_hat = hk.Linear(1, name="Predictor")(pred)
        y_hat = jax.nn.sigmoid(y_hat)

        # explain
        z_exp = jnp.concatenate((z, pred), axis=-1)
        cf = MLP(self.exp_sizes, self.dropout_rate, name="Explainer")(
            z_exp, is_training
        )
        cf = hk.Linear(input_shape, name="Explainer")(cf)
        return y_hat, cf


# %% ../../nbs/methods/04_counternet.ipynb 7
def partition_trainable_params(params: hk.Params, trainable_name: str):
    trainable_params, non_trainable_params = hk.data_structures.partition(
        lambda m, n, p: trainable_name in m, params
    )
    return trainable_params, non_trainable_params


# %% ../../nbs/methods/04_counternet.ipynb 8
class CounterNetTrainingModule(BaseTrainingModule):
    def __init__(self, config: CounterNetConfig | dict):
        self.save_hyperparameters(config.dict())
        self.configs = validate_configs(config, CounterNetConfig)
        self.net = make_hk_module(
            CounterNetModel,
            enc_sizes=config.enc_sizes,
            dec_sizes=config.pred_sizes,
            exp_sizes=config.exp_sizes,
            dropout_rate=config.dropout_rate
        )
        
        self.opt_1 = optax.adam(learning_rate=config.lr)
        self.opt_2 = optax.adam(learning_rate=config.lr)

    def init_net_opt(self, data_module: DataModule, key):
        # hook data_module
        self._data_module = data_module
        X, _ = data_module.sample(128)
        rng_key, key = random.split(key)

        # manually init multiple opts
        params, opt_1_state = init_net_opt(
            self.net, self.opt_1, X=X, key=rng_key
        )
        trainable_params, _ = partition_trainable_params(
            params, trainable_name="counter_net_model/Explainer"
        )
        opt_2_state = self.opt_2.init(trainable_params)
        return params, (opt_1_state, opt_2_state)

    @partial(jax.jit, static_argnames=["self", "is_training"])
    def forward(self, params, rng_key, x, is_training: bool = True):
        # first forward to get y_pred and normalized cf
        y_pred, cf = self.net.apply(params, rng_key, x, is_training=is_training)
        cf = self._data_module.apply_constraints(x, cf, hard=not is_training)

        # second forward to calulate cf_y
        cf_y, _ = self.net.apply(params, rng_key, cf, is_training=is_training)
        return y_pred, cf, cf_y

    @partial(jax.jit, static_argnames=["self"])
    def pred_fn(self, params, rng_key, xs):
        y_pred, _ = self.net.apply(params, rng_key, xs, is_training=False)
        return y_pred
    
    @partial(jax.jit, static_argnames=["self"])
    def generate_cf(self, params, rng_key, x):
        y_pred, cf = self.net.apply(params, rng_key, x, is_training=False)
        cf = self._data_module.apply_constraints(x, cf, hard=True)
        return cf

    @partial(jax.jit, static_argnames=["self"])
    def loss_fn_1(self, y_pred, y):
        return jnp.mean(vmap(optax.l2_loss)(y_pred, y))

    @partial(jax.jit, static_argnames=["self"])
    def loss_fn_2(self, cf_y, y_prime):
        return jnp.mean(vmap(optax.l2_loss)(cf_y, y_prime))

    @partial(jax.jit, static_argnames=["self"])
    def loss_fn_3(self, x, cf):
        return jnp.mean(vmap(optax.l2_loss)(x, cf))

    @partial(jax.jit, static_argnames=["self", "is_training"])
    def pred_loss_fn(self, params, rng_key, batch, is_training: bool = True):
        x, y = batch
        y_pred, cf = self.net.apply(params, rng_key, x, is_training=is_training)
        return self.configs.lambda_1 * self.loss_fn_1(y_pred, y)

    @partial(jax.jit, static_argnames=["self", "is_training"])
    def exp_loss_fn(
        self,
        trainable_params,
        non_trainable_params,
        rng_key,
        batch,
        is_training: bool = True,
    ):
        # merge trainable and non_trainable params
        params = hk.data_structures.merge(trainable_params, non_trainable_params)
        x, y = batch
        y_pred, cf, cf_y = self.forward(params, rng_key, x, is_training=is_training)
        y_prime = 1 - jnp.round(y_pred)
        loss_2, loss_3 = self.loss_fn_2(cf_y, y_prime), self.loss_fn_3(x, cf)
        return self.configs.lambda_2 * loss_2 + self.configs.lambda_3 * loss_3

    @partial(jax.jit, static_argnames=["self",])
    def _predictor_step(self, params, opt_state, rng_key, batch):
        grads = jax.grad(self.pred_loss_fn)(params, rng_key, batch)
        upt_params, opt_state = grad_update(grads, params, opt_state, self.opt_1)
        return upt_params, opt_state

    @partial(jax.jit, static_argnames=["self",])
    def _explainer_step(self, params, opt_state, rng_key, batch):
        trainable_params, non_trainable_params = partition_trainable_params(
            params, trainable_name="counter_net_model/Explainer"
        )
        grads = jax.grad(self.exp_loss_fn)(
            trainable_params, non_trainable_params, rng_key, batch
        )
        upt_trainable_params, opt_state = grad_update(
            grads, trainable_params, opt_state, self.opt_2
        )
        upt_params = hk.data_structures.merge(
            upt_trainable_params, non_trainable_params
        )
        return upt_params, opt_state

    @partial(jax.jit, static_argnames=["self"])
    def _training_step(
        self,
        params: hk.Params,
        opts_state: Tuple[optax.OptState, optax.OptState],
        rng_key: random.PRNGKey,
        batch: Tuple[Array, Array],
    ):
        opt_1_state, opt_2_state = opts_state
        params, opt_1_state = self._predictor_step(params, opt_1_state, rng_key, batch)
        upt_params, opt_2_state = self._explainer_step(
            params, opt_2_state, rng_key, batch
        )
        return upt_params, (opt_1_state, opt_2_state)

    @partial(jax.jit, static_argnames=["self"])
    def _training_step_logs(self, params, rng_key, batch):
        x, y = batch
        y_pred, cf, cf_y = self.forward(params, rng_key, x, is_training=False)
        y_prime = 1 - jnp.round(y_pred)

        loss_1, loss_2, loss_3 = (
            self.loss_fn_1(y_pred, y),
            self.loss_fn_2(cf_y, y_prime),
            self.loss_fn_3(x, cf),
        )
        logs = {
            "train/train_loss_1": loss_1,#.item(),
            "train/train_loss_2": loss_2,#.item(),
            "train/train_loss_3": loss_3,#.item(),
        }
        return logs

    @partial(jax.jit, static_argnames=["self"])
    def training_step(
        self,
        params: hk.Params,
        opts_state: Tuple[optax.OptState, optax.OptState],
        rng_key: random.PRNGKey,
        batch: Tuple[jnp.array, jnp.array],
    ) -> Tuple[hk.Params, Tuple[optax.OptState, optax.OptState]]:
        upt_params, (opt_1_state, opt_2_state) = self._training_step(
            params, opts_state, rng_key, batch
        )

        logs = self._training_step_logs(upt_params, rng_key, batch)
        return logs, (upt_params, (opt_1_state, opt_2_state))

    @partial(jax.jit, static_argnames=["self"])
    def validation_step(self, params, rng_key, batch):
        x, y = batch
        y_pred, cf, cf_y = self.forward(params, rng_key, x, is_training=False)
        y_prime = 1 - jnp.round(y_pred)

        loss_1, loss_2, loss_3 = (
            self.loss_fn_1(y_pred, y),
            self.loss_fn_2(cf_y, y_prime),
            self.loss_fn_3(x, cf),
        )
        # loss_1, loss_2, loss_3 = map(np.asarray, (loss_1, loss_2, loss_3))
        logs = {
            # "val/accuracy": accuracy(y, y_pred),
            # "val/validity": accuracy(cf_y, y_prime),
            # "val/proximity": compute_proximity(x, cf),
            "val/val_loss_1": loss_1,
            "val/val_loss_2": loss_2,
            "val/val_loss_3": loss_3,
            "val/val_loss": loss_1 + loss_2 + loss_3,
        }
        return logs

# %% ../../nbs/methods/04_counternet.ipynb 13
class CounterNetConfig(BaseConfig):
    """Configurator of `CounterNet`."""

    enc_sizes: List[int] = Field(
        [50,10], description="Sequence of layer sizes for encoder network."
    )
    pred_sizes: List[int] = Field(
        [10], description="Sequence of layer sizes for predictor."
    ) 
    exp_sizes: List[int] = Field(
        [50, 50], description="Sequence of layer sizes for CF generator."
    )
    
    dropout_rate: float = Field(
        0.3, description="Dropout rate."
    )
    lr: float = Field(
        0.003, description="Learning rate for training `CounterNet`."
    ) 
    lambda_1: float = Field(
        1.0, description=" $\lambda_1$ for balancing the prediction loss $\mathcal{L}_1$."
    ) 
    lambda_2: float = Field(
        0.2, description=" $\lambda_2$ for balancing the prediction loss $\mathcal{L}_2$."
    ) 
    lambda_3: float = Field(
        0.1, description=" $\lambda_3$ for balancing the prediction loss $\mathcal{L}_3$."
    )


# %% ../../nbs/methods/04_counternet.ipynb 14
class CounterNet(ParametricCFModule, PredFnMixedin):
    """API for CounterNet Explanation Module."""

    def __init__(
        self, 
        config: dict | CounterNetConfig = None,
        cfnet_module: CounterNetTrainingModule = None, 
        name: str = None
    ):
        if config is None:
            config = CounterNetConfig()
        config = validate_configs(config, CounterNetConfig)
        name = "CounterNet" if name is None else name
        self.module = cfnet_module
        self._is_trained = False
        super().__init__(config, name=name)

    def _init_model(self, config: CounterNetConfig, cfnet_module: CounterNetTrainingModule):
        if cfnet_module is None:
            cfnet_module = CounterNetTrainingModule(config)
        return cfnet_module
    
    @property
    def is_trained(self) -> bool:
        return self._is_trained

    def train(
        self, 
        data: DataModule, # data module
        batch_size: int = 128,
        epochs: int = 10,
        **kwargs
    ):
        self.module = self._init_model(self.config, self.module)
        self.params, _ = train_model(
            self.module, data, batch_size=batch_size, epochs=epochs, **kwargs
        )
        self._is_trained = True
        return self

    @auto_reshaping('x')
    def generate_cf(self, x: jax.Array, rng_key=jrand.PRNGKey(0), **kwargs) -> jax.Array:
        return self.module.generate_cf(self.params, rng_key=rng_key, x=x)
    
    def pred_fn(self, xs: jax.Array):
        y_pred = self.module.pred_fn(self.params, rng_key=jrand.PRNGKey(0), xs=xs)
        return y_pred

