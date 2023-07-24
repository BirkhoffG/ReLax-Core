# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/methods/08_clue.ipynb.

# %% ../../nbs/methods/08_clue.ipynb 3
from __future__ import annotations
from ..import_essentials import *
from .base import BaseCFModule, BaseParametricCFModule
from ..utils import *
from ..module import MLP, BaseTrainingModule
from ..data import *
from ..trainer import train_model, TrainingConfigs
from jax.scipy.stats.norm import logpdf as gaussian_logpdf


# %% auto 0
__all__ = ['Encoder', 'Decoder', 'kl_divergence', 'VAEGaussCatConfigs', 'VAEGaussCat', 'CLUEConfigs', 'CLUE']

# %% ../../nbs/methods/08_clue.ipynb 4
class Encoder(hk.Module):
    def __init__(self, sizes: List[int], dropout: float = 0.1):
        super().__init__()
        assert sizes[-1] % 2 == 0, f"sizes[-1] must be even, but got {sizes[-1]}"
        self.encoder = MLP(
            sizes, dropout_rate=dropout, name="encoder_mean")
    
    def __call__(self, x: Array, is_training: bool):
        params = self.encoder(x, is_training)
        d = params.shape[-1] // 2
        mu, sigma = params[:, :d], params[:, d:]
        sigma = jax.nn.softplus(sigma)
        sigma = jnp.clip(sigma, 1e-3)
        return mu, sigma

class Decoder(hk.Module):
    def __init__(
        self, 
        sizes: List[int], 
        input_size: int,
        dropout: float = 0.1
    ):
        super().__init__()
        self.decoder = MLP(
            sizes, dropout_rate=dropout, name="Decoder")
        self.input_size = input_size
    
    def __call__(self, z: Array, is_training: bool):
        mu_dec = self.decoder(z, is_training=is_training)
        mu_dec = hk.Linear(self.input_size, name='mu_x')(mu_dec)
        mu_dec = jax.nn.sigmoid(mu_dec)
        return mu_dec


# %% ../../nbs/methods/08_clue.ipynb 5
@jit
def kl_divergence(p: Array, q: Array, eps: float = 2 ** -17) -> Array:
    loss_pointwise = p * (jnp.log(p + eps) - jnp.log(q + eps))
    return loss_pointwise

# %% ../../nbs/methods/08_clue.ipynb 6
class VAEGaussCatConfigs(BaseParser):
    lr: float = Field(0.001, description="Learning rate.")
    enc_sizes: List[int] = Field(
        [20, 16, 14, 12],
        description="Sequence of Encoder layer sizes."
    )
    dec_sizes: List[int] = Field(
        [12, 14, 16, 20],
        description="Sequence of Decoder layer sizes."
    )
    dropout_rate: float = Field(
        0.1, description="Dropout rate."
    )



# %% ../../nbs/methods/08_clue.ipynb 7
class VAEGaussCat(BaseTrainingModule):
    def __init__(self, m_configs: Dict = None):
        if m_configs is None: m_configs = {}
        self.save_hyperparameters(m_configs)
        self.m_config = validate_configs(m_configs, VAEGaussCatConfigs)
        self.opt = optax.radam(self.m_config.lr)

    def _update_categorical_info(self):
        cat_arrays = self._data_module._cat_arrays
        self._cat_info = {
            'cat_idx': self._data_module.cat_idx,
            # 'cat_arr': jnp.array([len(cat_arr) for cat_arr in cat_arrays]),
            'cat_arr': [len(cat_arr) for cat_arr in cat_arrays],
        }
    
    def init_net_opt(self, dm, key):
        self._data_module = dm
        self._update_categorical_info()
        keys = jax.random.split(key, 3)
        X, y = dm.train_dataset[:128]
        Z = jnp.ones((X.shape[0], self.m_config.enc_sizes[-1] // 2))

        self.encoder = make_hk_module(
            Encoder, sizes=self.m_config.enc_sizes, 
            dropout=self.m_config.dropout_rate
        )
        self.decoder = make_hk_module(
            Decoder, sizes=self.m_config.dec_sizes,
            input_size=X.shape[-1], 
            dropout=self.m_config.dropout_rate
        )

        enc_params = self.encoder.init(
            keys[0], X, is_training=True)
        dec_params = self.decoder.init(
            keys[1], Z, is_training=True)
        opt_state = self.opt.init((enc_params, dec_params))

        # set prior for training latents
        self.prior = jrand.normal(
            keys[2], (self.m_config.enc_sizes[-1],)
        )
        return (enc_params, dec_params), opt_state
    
    @partial(jax.jit, static_argnums=(0, 4))
    def encode(self, enc_params, rng_key, x, is_training=True):
        mu_z, var_z = self.encoder.apply(
            enc_params, rng_key, x, is_training=is_training)
        return mu_z, var_z
    
    @partial(jax.jit, static_argnums=(0, ))
    def sample_latent(self, rng_key, mean, var):
        key, _ = jax.random.split(rng_key)
        std = jnp.exp(0.5 * var)
        eps = jax.random.normal(key, var.shape)
        return mean + eps * std
    
    @partial(jax.jit, static_argnums=(0, 4))
    def decode(self, dec_params, rng_key, z, is_training=True,):
        reconstruct_x = self.decoder.apply(
            dec_params, rng_key, z, is_training=is_training)
        return reconstruct_x        
    
    @partial(jax.jit, static_argnums=(0, 5))
    def sample_step(
        self, rng_key, dec_params, mean, var, is_training=True
    ):
        z = self.sample_latent(rng_key, mean, var)
        mu_x = self.decode(dec_params, rng_key, z, is_training=is_training)
        return mu_x
    
    @partial(jax.jit, static_argnums=(0, 4, 5))
    def sample(
        self, params, rng_key, x, mc_samples, is_training=True
    ): # Shape: (mc_samples, batch_size, input_size)
        enc_params, dec_params = params
        mean, var = self.encode(enc_params, rng_key, x, is_training=is_training)
        keys = jax.random.split(rng_key, mc_samples)
        
        partial_sample_step = partial(
            self.sample_step, dec_params=dec_params,
            mean=mean, var=var, is_training=is_training
        )
        reconstruct_x = jax.vmap(partial_sample_step)(keys)
        return (mean, var, reconstruct_x)
    
    @partial(jax.jit, static_argnums=(0, ))
    def sample_prior(self, rng_key):
        rng_key, key = jax.random.split(rng_key)
        prior = jrand.normal(key, (self.m_config.enc_sizes[-1],))
        return prior
    
    def compute_loss(self, params, rng_key, x, is_training=True):
        # @partial(jax.jit, static_argnums=(2, 3))
        def reconstruct_loss(x: Array, cf: Array, cat_idx: int, cat_arr: List[int]):
            
            def compute_cat_loss(cat_arr):
                if len(cat_arr) == 0: return jnp.zeros((x.shape[0], 0))
                
                cat_loss = []

                def _cat_loss_f(start_end_idx):
                    start_idx, end_idx = start_end_idx
                    return optax.softmax_cross_entropy(
                        cf[:, start_idx: end_idx], x[:, start_idx: end_idx]
                    ).reshape(-1, 1)
                
                # for start_end_idx in start_end_indices:
                start_idx = cat_idx
                for i, cat in enumerate(cat_arr):
                    end_idx = start_idx + cat
                    start_end_idx = (start_idx, end_idx)
                    cat_loss.append(_cat_loss_f(start_end_idx))
                    start_idx = end_idx
                cat_loss = jnp.concatenate(cat_loss, axis=-1)
                return cat_loss
            
            # cat_loss = jax.vmap(jit(_cat_loss_f))(start_indices, end_indices)
            # cat_loss = jax.lax.scan(_cat_loss_f, 0., start_end_indices, len(start_end_indices))[1]
            cont_loss = optax.l2_loss(x[:, :cat_idx], cf[:, :cat_idx])
            cat_loss = compute_cat_loss(cat_arr)
            return jnp.concatenate([cont_loss, cat_loss], axis=-1).sum(-1)
        
        keys = jax.random.split(rng_key, 2)
        mu_z, logvar_z, reconstruct_x = self.sample(
            params, keys[0], x, mc_samples=1, is_training=is_training
        )
        kl_loss = -0.5 * (1 + logvar_z - jnp.power(mu_z, 2) - jnp.exp(logvar_z)).sum(-1)
        
        rec = reconstruct_loss(
            x, reconstruct_x.reshape(x.shape), 
            cat_idx=self._cat_info['cat_idx'],
            cat_arr=self._cat_info['cat_arr']
        ).sum(-1)
        batchwise_loss = (rec + kl_loss) / x.shape[0]
        return batchwise_loss.mean()

    @partial(jax.jit, static_argnums=(0,))
    def _training_step(
        self, 
        params: Tuple[hk.Params, hk.Params],
        opt_state: optax.OptState, 
        rng_key: random.PRNGKey, 
        batch: Tuple[Array, Array]
    ) -> Tuple[hk.Params, optax.OptState]:
        x, _ = batch
        loss, grads = jax.value_and_grad(self.compute_loss)(
            params, rng_key, x)
        update_params, opt_state = grad_update(
            grads, params, opt_state, self.opt)
        return update_params, opt_state, loss

    def training_step(
        self,
        params: Tuple[hk.Params, hk.Params],
        opt_state: optax.OptState,
        rng_key: random.PRNGKey,
        batch: Tuple[jnp.array, jnp.array]
    ) -> Tuple[hk.Params, optax.OptState]:
        params, opt_state, loss = self._training_step(params, opt_state, rng_key, batch)
        self.log_dict({'train/loss': loss.item()})
        return params, opt_state
    
    @partial(jax.jit, static_argnums=(0,))
    def validation_step(
        self,
        params: Tuple[hk.Params, hk.Params],
        rng_key: random.PRNGKey,
        batch: Tuple[jnp.array, jnp.array],
    ) -> Tuple[hk.Params, optax.OptState]:
        pass


# %% ../../nbs/methods/08_clue.ipynb 8
@auto_reshaping('x')
def _clue_generate(
    x: Array,
    rng_key: jrand.PRNGKey,
    pred_fn: Callable,
    max_steps: int,
    step_size: float,
    vae_module: VAEGaussCat,
    vae_params: Tuple[hk.Params, hk.Params],
    uncertainty_weight: float,
    aleatoric_weight: float,
    prior_weight: float,
    distance_weight: float,
    validity_weight: float,
    apply_fn: Callable
) -> Array:
    
    @jit
    def sample_latent_from_x(
        x: Array, enc_params: hk.Params, rng_key: jrand.PRNGKey
    ):
        key_1, key_2 = jrand.split(rng_key)
        mean, var = vae_module.encode(enc_params, key_1, x, is_training=False)
        z = vae_module.sample_latent(key_2, mean, var)
        return z
    
    @partial(jit, static_argnums=(2,))
    def generate_from_z(
        z: Array, 
        dec_params: hk.Params,
        hard: bool = False
    ):
        cf = vae_module.decode(
            dec_params, rng_key, z, is_training=False)
        cf = apply_fn(x, cf, hard=hard)
        return cf

    @jit
    def uncertainty_from_z(z: Array, dec_params: hk.Params):
        cfs = generate_from_z(z, dec_params, hard=False)
        prob = pred_fn(cfs)
        total_uncertainty = -(prob * jnp.log(prob + 1e-10)).sum(-1)
        return total_uncertainty, cfs, prob
    
    @jit
    def compute_loss(z: Array, dec_params: hk.Params):
        uncertainty, cfs, prob = uncertainty_from_z(z, dec_params)
        loglik = gaussian_logpdf(z).sum(-1)
        dist = jnp.abs(cfs - x).mean()
        validity = binary_cross_entropy(preds=prob, labels=y_targets).mean()
        loss = (
            (uncertainty_weight + aleatoric_weight) * uncertainty 
            + prior_weight * loglik
            + distance_weight * dist
            + validity_weight * validity
        )
        return loss.mean()
    
    @loop_tqdm(max_steps)
    def step(i, z_opt_state):
        z, opt_state = z_opt_state
        z_grad = jax.grad(compute_loss)(z, dec_params)
        z, opt_state = grad_update(z_grad, z, opt_state, opt)
        return z, opt_state
    
    enc_params, dec_params = vae_params
    key_1, _ = jax.random.split(rng_key)
    z = sample_latent_from_x(x, enc_params, key_1)
    opt = optax.adam(step_size)
    opt_state = opt.init(z)
    y_targets = 1 - pred_fn(x)

    # Write a loop to optimize z using lax.fori_loop
    z, opt_state = lax.fori_loop(0, max_steps, step, (z, opt_state))
    cf = generate_from_z(z, dec_params, hard=True)
    return cf


# %% ../../nbs/methods/08_clue.ipynb 9
class CLUEConfigs(BaseParser):
    enc_sizes: List[int] = Field(
        [20, 16, 14, 12], description="Sequence of Encoder layer sizes."
    )
    dec_sizes: List[int] = Field(
        [12, 14, 16, 20], description="Sequence of Decoder layer sizes."
    )
    encoded_size: int = Field(5, description="Encoded size")
    lr: float = Field(0.001, description="Learning rate")
    max_steps: int = Field(500, description="Max steps")
    step_size: float = Field(0.01, description="Step size")
    vae_n_epochs: int = Field(10, description="Number of epochs for VAE")
    vae_batch_size: int = Field(128, description="Batch size for VAE")
    seed: int = Field(0, description="Seed for random number generator")

# %% ../../nbs/methods/08_clue.ipynb 10
class CLUE(BaseCFModule, BaseParametricCFModule):
    params: Tuple[hk.Params, hk.Params] = None
    module: VAEGaussCat
    name: str = 'CLUE'

    def __init__(self, m_config: Dict | CLUEConfigs = None):
        if m_config is None:
            m_config = CLUEConfigs()
        self.m_config = validate_configs(m_config, CLUEConfigs)
        self.module = VAEGaussCat(self.m_config.dict())
        self.rng_key = random.PRNGKey(self.m_config.seed)

    def _is_module_trained(self) -> bool:
        return not (self.params is None)
    
    def train(
        self, 
        datamodule: TabularDataModule, # data module
        t_configs: TrainingConfigs | dict = None, # training configs
        *args, **kwargs
    ):
        _default_t_configs = dict(
            n_epochs=10, batch_size=128
        )
        if t_configs is None: t_configs = _default_t_configs
        params, _ = train_model(self.module, datamodule, t_configs)
        self.params = params

    def generate_cf(self, x, pred_fn: Callable = None) -> Array:
        return _clue_generate(
            x, 
            rng_key=self.rng_key, 
            pred_fn=pred_fn,
            max_steps=self.m_config.max_steps,
            step_size=self.m_config.step_size,
            vae_module=self.module,
            vae_params=self.params,
            uncertainty_weight=.0,
            aleatoric_weight=0.0,
            prior_weight=0.0,
            distance_weight=.1,
            validity_weight=1.0,
            apply_fn=self.data_module.apply_constraints,
        )
    
    def generate_cfs(self, X: Array, pred_fn: Callable = None) -> jnp.ndarray:
        generate_cf_partial = partial(
            self.generate_cf, pred_fn=pred_fn
        )
        rngs = lax.broadcast(random.PRNGKey(0), (X.shape[0], ))
        return jax.vmap(generate_cf_partial)(X, rngs)