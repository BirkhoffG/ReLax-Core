# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/06_evaluate.ipynb.

# %% ../nbs/06_evaluate.ipynb 3
from __future__ import annotations
from .import_essentials import *
from .train import train_model, TensorboardLogger
from .datasets import TabularDataModule
from .utils import accuracy, proximity
from .methods.base import BaseCFModule, ParametricCFModule
from .methods.counternet import CounterNet
from copy import deepcopy
from sklearn.neighbors import NearestNeighbors


# %% auto 0
__all__ = ['CFExplanationResults', 'metrics2fn', 'DEFAULT_METRICS', 'Explanation', 'generate_cf_explanations',
           'generate_cf_results_local_exp', 'generate_cf_results_cfnet', 'compute_predictive_acc', 'compute_validity',
           'compute_proximity', 'compute_sparsity', 'compute_manifold_dist', 'get_runtime', 'compute_so_validity',
           'compute_so_proximity', 'compute_so_sparsity', 'evaluate_cfs', 'benchmark_cfs']

# %% ../nbs/06_evaluate.ipynb 4
@dataclass
class Explanation:
    """Generated CF Explanations class."""
    cf_name: str  # cf method's name
    data_module: TabularDataModule  # data module
    cfs: jnp.DeviceArray  # generated cf explanation of `X`
    total_time: float  # total runtime
    pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray]  # predict function
    dataset_name: str = str()  # dataset name
    X: jnp.ndarray = None  # input
    y: jnp.ndarray = None  # label

    def __post_init__(self):
        if self.data_module:
            if self.dataset_name == str():
                self.dataset_name = self.data_module.data_name
            test_X, label = self.data_module.test_dataset[:]
            if self.X is None:
                self.X = test_X
            if self.y is None:
                self.y = label

CFExplanationResults = Explanation

# %% ../nbs/06_evaluate.ipynb 8
def _prepare_module(
    cf_module: BaseCFModule,
    datamodule: TabularDataModule
):
    cf_module.update_cat_info(datamodule)
    return cf_module

def _train_parametric_module(
    cf_module: BaseCFModule,
    datamodule: TabularDataModule,
    t_configs=None
):
    print(f'{type(cf_module)} contains parametric models. '
        'Starts training before generating explanations...')
    cf_module.train(datamodule, t_configs)
    return cf_module

def _check_pred_fn(pred_fn, cf_module):
    if pred_fn is None:
        try:
            pred_fn = cf_module.pred_fn
        except AttributeError:
            raise AttributeError(
                    "`generate_cf_explanations` is incorrectly configured."
                    f"It is supposed to be `pred_fn != None`,"
                    f"or {type(cf_module)} has attribute `pred_fn`."
                    f"However, we got `pred_fn={pred_fn}`, "
                    f"and cf_module=`{type(cf_module)}` contains no `pred_fn`."
            )
    return pred_fn

# %% ../nbs/06_evaluate.ipynb 9
def generate_cf_explanations(
    cf_module: BaseCFModule,
    datamodule: TabularDataModule,
    pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray] = None,
    *,
    t_configs=None
) -> Explanation:
    """Generate CF explanations."""
    cf_module = _prepare_module(cf_module, datamodule)

    if isinstance(cf_module, ParametricCFModule):
        cf_module = _train_parametric_module(
            cf_module, datamodule, t_configs=t_configs
        )
    X, _ = datamodule.test_dataset[:]

    # generate cfs
    current_time = time.time()
    cfs = cf_module.generate_cfs(X, pred_fn=pred_fn)
    total_time = time.time() - current_time
    # check pred_fn
    pred_fn = _check_pred_fn(pred_fn, cf_module)

    return Explanation(
        cf_name=cf_module.name,
        data_module=datamodule,
        cfs=cfs,
        total_time=total_time,
        pred_fn=pred_fn,
    )

# def generate_cf_results(
#     cf_module: BaseCFExplanationModule,
#     dm: TabularDataModule,
#     pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray] = None,
#     params: hk.Params = None,  # params of `cf_module`
#     rng_key: Optional[random.PRNGKey] = None,
# ) -> CFExplanationResults:
#     # validate arguments
#     if (pred_fn is None) and (params is None) and (rng_key is None):
#         raise ValueError(
#             "A valid `pred_fn: Callable[jnp.DeviceArray], jnp.DeviceArray]` or `params: hk.Params` needs to be passed."
#         )
#     # prepare
#     X, y = dm.test_dataset[:]
#     cf_module.update_cat_info(dm)
#     # generate cfs
#     current_time = time.time()
#     if pred_fn:
#         cfs = cf_module.generate_cfs(X, pred_fn)
#     else:
#         cfs = cf_module.generate_cfs(X, params, rng_key)
#         pred_fn = lambda x: cf_module.predict(deepcopy(params), rng_key, x)
#     total_time = time.time() - current_time

#     return CFExplanationResults(
#         cf_name=cf_module.name,
#         data_module=dm,
#         cfs=cfs,
#         total_time=total_time,
#         pred_fn=pred_fn,
#     )
    # return CFExplanationResults(
    #     X=X, y=y, cfs=cfs, total_time=total_time,
    #     pred_fn=pred_fn,
    #     cf_name=cf_module.name, dataset_name=dm.data_name
    # )



# %% ../nbs/06_evaluate.ipynb 10
@deprecated(removed_in='0.1.0', deprecated_in='0.0.9')
def generate_cf_results_local_exp(
    cf_module: BaseCFModule,
    dm: TabularDataModule,
    pred_fn: Callable[[jnp.DeviceArray], jnp.DeviceArray],
) -> CFExplanationResults:
    return generate_cf_explanations(cf_module, dm, pred_fn=pred_fn)


@deprecated(removed_in='0.1.0', deprecated_in='0.0.9')
def generate_cf_results_cfnet(
    cf_module: CounterNet,
    dm: TabularDataModule,
    params: hk.Params = None,  # params of `cf_module`
    rng_key: random.PRNGKey = None,
) -> CFExplanationResults:
    return generate_cf_explanations(cf_module, dm, pred_fn=None)


# %% ../nbs/06_evaluate.ipynb 12
def compute_predictive_acc(cf_results: CFExplanationResults):
    X, y = cf_results.data_module.test_dataset[:]
    pred_fn = cf_results.pred_fn

    y_pred = pred_fn(X).reshape(-1, 1)
    label = y.reshape(-1, 1)
    return accuracy(jnp.round(y_pred), label).item()


def compute_validity(cf_results: CFExplanationResults):
    X, y = cf_results.data_module.test_dataset[:]
    pred_fn = cf_results.pred_fn

    y_pred = pred_fn(X).reshape(-1, 1).round()
    y_prime = 1 - y_pred
    cf_y = pred_fn(cf_results.cfs).reshape(-1, 1).round()
    return accuracy(y_prime, cf_y).item()


def compute_proximity(cf_results: CFExplanationResults):
    X, y = cf_results.data_module.test_dataset[:]
    return proximity(X, cf_results.cfs).item()


def compute_sparsity(cf_results: CFExplanationResults):
    X, y = cf_results.data_module.test_dataset[:]
    cfs = cf_results.cfs
    cat_idx = cf_results.data_module.cat_idx
    # calculate sparsity
    cat_sparsity = proximity(X[:, cat_idx:], cfs[:, cat_idx:]) / 2
    cont_sparsity = jnp.linalg.norm(
        jnp.abs(X[:, :cat_idx] - cfs[:, :cat_idx]), ord=0, axis=1
    ).mean()
    return cont_sparsity + cat_sparsity


def compute_manifold_dist(cf_results: CFExplanationResults):
    X, y = cf_results.data_module.test_dataset[:]
    cfs = cf_results.cfs
    knn = NearestNeighbors()
    knn.fit(X)
    nearest_dist, nearest_points = knn.kneighbors(cfs, 1, return_distance=True)
    return jnp.mean(nearest_dist).item()


def get_runtime(cf_results: CFExplanationResults):
    return cf_results.total_time


def _create_second_order_cfs(cf_results: CFExplanationResults, threshold: float = 2.0):
    X, y = cf_results.data_module.test_dataset[:]
    cfs = cf_results.cfs
    scaler = cf_results.data_module.normalizer
    cat_idx = cf_results.data_module.cat_idx

    # get normalized threshold = threshold / (max - min)
    data_range = scaler.data_range_
    thredshold_normed = threshold / data_range

    # select continous features
    x_cont = X[:, :cat_idx]
    cf_cont = cfs[:, :cat_idx]
    # calculate the diff between x and c
    cont_diff = jnp.abs(x_cont - cf_cont) <= thredshold_normed
    # new cfs
    cfs_cont_hat = jnp.where(cont_diff, x_cont, cf_cont)

    cfs_hat = jnp.concatenate((cfs_cont_hat, cfs[:, cat_idx:]), axis=-1)
    return cfs_hat


def compute_so_validity(cf_results: CFExplanationResults, threshold: float = 2.0):
    cfs_hat = _create_second_order_cfs(cf_results, threshold)
    cf_results_so = deepcopy(cf_results)
    cf_results_so.cfs = cfs_hat
    return compute_validity(cf_results_so)


def compute_so_proximity(cf_results: CFExplanationResults, threshold: float = 2.0):
    cfs_hat = _create_second_order_cfs(cf_results, threshold)
    cf_results_so = deepcopy(cf_results)
    cf_results_so.cfs = cfs_hat
    return compute_proximity(cf_results_so)


def compute_so_sparsity(cf_results: CFExplanationResults, threshold: float = 2.0):
    cfs_hat = _create_second_order_cfs(cf_results, threshold)
    cf_results_so = deepcopy(cf_results)
    cf_results_so.cfs = cfs_hat
    return compute_sparsity(cf_results_so)


# %% ../nbs/06_evaluate.ipynb 13
metrics2fn = {
    "acc": compute_predictive_acc,
    "validity": compute_validity,
    "proximity": compute_proximity,
    "runtime": get_runtime,
    "manifold_dist": compute_manifold_dist,
    "so_validity": compute_so_validity,
    "so_proximity": compute_so_proximity,
    "so_sparsity": compute_so_sparsity,
}


# %% ../nbs/06_evaluate.ipynb 14
DEFAULT_METRICS = ["acc", "validity", "proximity"]


def evaluate_cfs(
    cf_results: CFExplanationResults,
    metrics: Optional[Iterable[str]] = None,
    return_dict: bool = True,
    return_df: bool = False,
):
    cf_name = cf_results.cf_name
    data_name = cf_results.data_module.data_name
    result_dict = {(data_name, cf_name): dict()}
    if metrics is None:
        metrics = DEFAULT_METRICS

    for metric in metrics:
        result_dict[(data_name, cf_name)][metric] = metrics2fn[metric](cf_results)
    result_df = pd.DataFrame.from_dict(result_dict, orient="index")
    if return_dict and return_df:
        return (result_dict, result_df)
    elif return_dict or return_df:
        return result_df if return_df else result_dict


# %% ../nbs/06_evaluate.ipynb 15
def benchmark_cfs(
    cf_results_list: Iterable[CFExplanationResults],
    metrics: Optional[Iterable[str]] = None,
):
    dfs = [
        evaluate_cfs(
            cf_results=cf_results, metrics=metrics, return_dict=False, return_df=True
        )
        for cf_results in cf_results_list
    ]
    return pd.concat(dfs)
