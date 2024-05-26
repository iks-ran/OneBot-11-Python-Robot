from omegaconf.dictconfig import DictConfig
from colorlog import ColoredFormatter
from omegaconf import OmegaConf
import functools
import importlib
import traceback
import logging

def handle_exceptions_for_methods(cls):
    for name, method in vars(cls).items():
        if callable(method):
            setattr(cls, name, handle_exceptions(method))
    return cls

def handle_exceptions(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(__name__)
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            error_msg = "Exception in '{}': {}".format(func.__name__, e)
            traceback_str = traceback.format_exc()
            logger.error(error_msg)
            logger.error("Traceback: {}".format(traceback_str))
    return wrapper

@handle_exceptions
def setup_logger(log_file_path, debug=False):

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    formatter = ColoredFormatter(
        '%(asctime)s - %(log_color)s[%(levelname)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'green',
            'INFO': 'white',
            'WARNING': 'yellow',
            'ERROR': 'red',
        }
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s]: %(message)s'))
    logger.addHandler(file_handler)

    return logger

@handle_exceptions
def instantiate_from_config(config, isfunc=True, add_params=dict()):
    if isinstance(config, DictConfig):
        config = OmegaConf.to_container(config)
    if not "target" in config:
        raise KeyError("Expected key `target` to instantiate for config")
    module_name, target = config.pop("target").rsplit(".", 1)
    input_params = config.pop("params", dict())
    input_params.update(add_params)
    extra_params = config
    module = importlib.import_module(module_name, package=None)
    if isfunc:
        return getattr(module, target), input_params, extra_params
    else:
        return getattr(module, target)(**input_params)
    
@handle_exceptions
def is_request_success(response):
    return response.status_code == 200

@handle_exceptions
def synchronized(lock):
    def decorator(func):
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper
    return decorator

@handle_exceptions
def format_dict_keys(d, parent_key="", sep=".", rep="§"):
    formatted_dict = {}
    for key, value in d.items():
        new_key = f"{parent_key}{sep}{key.replace(sep, rep)}" if parent_key else key.replace(sep, rep)
        if isinstance(value, dict|DictConfig):
            formatted_dict.update(format_dict_keys(value, new_key))
        else:
            formatted_dict[new_key] = value
    return formatted_dict

@handle_exceptions
def unformat_dict_keys(d, sep=".", rep="§"):
    original_dict = {}
    for key, value in d.items():
        keys = key.split(sep)
        current_dict = original_dict
        for k in keys[:-1]:
            current_dict = current_dict.setdefault(k.replace(rep, sep), {})
        current_dict[keys[-1]] = value
    return original_dict

@handle_exceptions
def String2Dict(string: str, 
                default_key: str, 
                sep: str=";&amp;"):
    if sep not in string and default_key not in string:
        return {default_key: string}
    items = string.split(sep)
    return {item.split("=")[0]: item.split("=")[1] for item in items}

logger = setup_logger("OneBot.log", False)
