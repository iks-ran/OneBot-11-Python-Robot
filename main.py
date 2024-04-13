from utils import instantiate_from_config, logger
from omegaconf import OmegaConf
import argparse
import logging
import sys
import os

FILE_PATH = os.path.realpath(__file__)
WORKBENCH = os.path.dirname(FILE_PATH)
sys.path.append(WORKBENCH)
os.chdir(WORKBENCH)

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, default="./configs/last.yaml")
    parser.add_argument("-d", "--debug", action="store_true")
    return parser.parse_args()

if __name__ == "__main__":
    args = get_args()
    
    cfg_file = args.config
    if not os.path.exists(cfg_file):
        cfg_files = [os.path.join(WORKBENCH, "configs", f) for f in os.listdir(os.path.join(WORKBENCH, "configs")) if f.endswith(".yaml")]
        cfg_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        if len(cfg_files) == 0:
            raise FileNotFoundError("Target config file not found and no config file in ./configs")
        cfg_file = cfg_files[0]
        print("Target config file not found, use the latest config file {}".format(cfg_file))
    config = OmegaConf.load(cfg_file)
    
    logger.level = logging.DEBUG if args.debug else logging.INFO
    bot = instantiate_from_config(config, isfunc=False, add_params={"Logger": logger})
    bot.run()
    
    