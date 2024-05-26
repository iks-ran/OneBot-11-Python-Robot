from utils import handle_exceptions, format_dict_keys, unformat_dict_keys, logger
from omegaconf import OmegaConf
from io import BytesIO
from PIL import Image
import subprocess
import datetime
import random
import psutil
import signal
import os

@handle_exceptions
def Test(reply):
    return reply

@handle_exceptions
def CleanCache(bot): 
    return bot.clean_cache()

@handle_exceptions
def SaveConfig(bot, 
               save_dir: str="./configs", 
               prefix: str="last"):
    cfg = bot.get_config()
    config = OmegaConf.create({"target": "OneBot.OneBot", 
                               "params": cfg})
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    savepath = os.path.join(save_dir, f"{prefix}.yaml")
    if os.path.exists(savepath):
        os.rename(savepath, os.path.join(save_dir, "{}_{}.yaml".format(prefix, 
                                         datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))))
    
    OmegaConf.save(config, savepath)
    logger.info("Config saved to {}".format(savepath))
    return "配置已保存到 {}".format(savepath)

@handle_exceptions
def KillChildProcesses():
    logger.info("Kill child processes called")
    parent_pid = os.getpid()
    parent = psutil.Process(parent_pid)
    children = parent.children(recursive=True)
    
    for process in children:
        process.send_signal(signal.SIGKILL)
        logger.info("Kill child process {}".format(process.pid))
        
    return "已杀死所有子进程共 {} 个".format(len(children))

@handle_exceptions
def SaveImage(image: bytes,
              save_dir: str="./images", 
              prefix: str="image", 
              ext: str=".png"):
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    image = Image.open(BytesIO(image))
    savepath = os.path.join(save_dir, 
                            f"{prefix}_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}" + \
                            f"_{random.randint(0, 114514)}{ext}")
    image.save(savepath)
    abs_savepath = os.path.abspath(savepath)
    logger.info("Image saved to {}".format(abs_savepath))
    return abs_savepath

@handle_exceptions
def CleanFileCache(retained: int, 
                   save_dir: str):
    if not os.path.exists(save_dir):
        return "缓存目录不存在"
    files = os.listdir(save_dir)
    file_lists = [os.path.join(save_dir, file) for file in files]
    file_lists.sort(key=lambda x: os.path.getmtime(x))
    for file in file_lists[:-retained]:
        os.remove(file)
    logger.info("Remove {} files from file cache".format(len(files)-retained))
    return "保留 {} 个文件".format(retained)

@handle_exceptions
def ChangeAttribute(bot, 
                    message: str):
    show = False
    if message.endswith("|-s"):
        message = message[:-3]
        show = True
    key, value = message.split("=", 1)
    cmd_name, cmd_key = key.split(".", 1)
    if cmd_name not in bot.Commands.keys():
        return "未知命令 {}".format(cmd_name)
    commands = bot.Commands
    cmd_dict = commands[cmd_name]
    formatted_cmd_dict = format_dict_keys(cmd_dict)
    logger.debug("Formatted commands: {}".format(formatted_cmd_dict.keys()))
    logger.debug("Received key: {}, value: {} for command {}".format(cmd_key, value, cmd_name))
    if cmd_key not in formatted_cmd_dict:
        return "未找到属性 {}".format(cmd_key)
    if show:
        return "命令 {} 的属性 {} 为 {}".format(cmd_name, cmd_key, formatted_cmd_dict[cmd_key])
    if isinstance(formatted_cmd_dict[cmd_key], bool):
        if value.lower() in ["true", "false"]:
            value = value.lower() == "true"
            formatted_cmd_dict[cmd_key] = value
        else:
            return "布尔值只能为 True 或 False"
    elif isinstance(formatted_cmd_dict[cmd_key], int):
        try:
            value = int(value)
            formatted_cmd_dict[cmd_key] = value
        except:
            return "整数值格式错误"
    elif isinstance(formatted_cmd_dict[cmd_key], float):
        try:
            value = float(value)
            formatted_cmd_dict[cmd_key] = value
        except:
            return "浮点数值格式错误"
    elif isinstance(formatted_cmd_dict[cmd_key], str):
        formatted_cmd_dict[cmd_key] = value
    else:
        return "未知属性类型"
    
    unformatted_cmd_dict = unformat_dict_keys(formatted_cmd_dict)
    with bot.COMMAND_LOCK:
        commands[cmd_name] = unformatted_cmd_dict
        bot.Commands = commands
    logger.info("Attribute {} for command {} changed to {}".format(cmd_key, cmd_name, value))
        
    return "命令 {} 的属性 {} 已修改为 {}".format(cmd_name, cmd_key, value)

@handle_exceptions
def TerminalCommand(bot, 
                    message: str, 
                    sender_id: int):
    logger.debug("Terminal command received: {}".format(message))
    
    if not bot.is_admin(sender_id):
        logger.warning("Unauthorized user {} tried to execute terminal command".format(sender_id))
        return "权限不足, 仅限管理员执行"
    process = subprocess.Popen(message, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()
    result = out.decode("utf-8") + err.decode("utf-8")
    
    logger.debug("Terminal command executed, {}".format(result))
    return result.strip("\n")