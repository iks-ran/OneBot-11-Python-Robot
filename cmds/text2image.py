from utils import handle_exceptions, logger
from transformers import CLIPTokenizer
from cmds.utils import SaveImage
import traceback
import numpy as np
import requests
import traceback
import random

MAX_SEED = np.iinfo(np.int32).max
TOKENIZER = CLIPTokenizer.from_pretrained("openai/clip-vit-large-patch14")

def String2Dict(string: str):
    items = string.split(";&amp;")
    return {item.split("=")[0]: item.split("=")[1] for item in items}

@handle_exceptions
def PreprocessRawinput(raw_input: str, 
                       negative_prompt: str, 
                       quality: str, 
                       style: str, 
                       quality_dict: dict, 
                       style_dict: dict, 
                       custom_width: int=1024, 
                       custom_height: int=1024, 
                       return_url: bool=True):
    logger.debug("Get raw text: {}".format(raw_input))
    try:
        cfg = String2Dict(raw_input)
        prompt = cfg.get("prompt", "")
        negative_prompt = cfg.get("negative_prompt", negative_prompt)
        quality = cfg.get("quality", quality)
        style = cfg.get("style", style)
        custom_width = cfg.get("custom_width", custom_width)
        custom_height = cfg.get("custom_height", custom_height)
        
        new_prompt, new_negative_prompt = ExpandPrompt(prompt, negative_prompt, 
                                                       quality, style, quality_dict, 
                                                       style_dict)
        
        postdata = {"prompt": new_prompt, "negative_prompt": new_negative_prompt, 
                    "seed": random.randint(0, MAX_SEED), "add_quality_tags": False, 
                    "style_selector": "(None)", "quality_selector": "(None)", 
                    "custom_width": int(custom_width), "custom_height": int(custom_height), 
                    "aspect_ratio_selector": "Custom", "return_url": return_url}
        logger.debug("Get postdata: {}".format(postdata))
        
        return postdata
    
    except Exception as e:
        traceback_str = traceback.format_exc()
        return_str = "Exception in `PreprocessRawinput`: {}\n".format(e) + \
                     "Traceback: {}".format(traceback_str)
        logger.error(return_str)
        return return_str
    
@handle_exceptions
def ExpandPrompt(raw_prompt: str, 
                 raw_negative_prompt: str, 
                 quality: str, 
                 style: str, 
                 quality_dict: dict, 
                 style_dict: dict):
    quality_prompt, quality_negative_prompt = quality_dict.get(quality, quality_dict["Standard v3.1"]).values()
    style_prompt, style_negative_prompt = style_dict.get(style, style_dict["(None)"]).values()
    
    prompt = style_prompt.format(prompt=quality_prompt.format(prompt=raw_prompt))
    negative_prompt = quality_negative_prompt.format(
                      negative_prompt=style_negative_prompt.format(
                      negative_prompt=raw_negative_prompt))
    logger.debug("Expand prompt with quality prompts `{}` and style prompts `{}`".format(
                     quality_prompt, style_prompt))
    logger.debug("Expand negative prompt with quality prompts `{}` and style prompts `{}`".format(
                     quality_negative_prompt, style_negative_prompt))
    
    return prompt.strip().strip(",").strip(), negative_prompt.strip().strip(",").strip()

@handle_exceptions
def CheckTokenLength(message: str, 
                     negative_prompt: str, 
                     quality: str, 
                     style: str, 
                     quality_dict: dict, 
                     style_dict: dict, 
                     max_length=77):
    negative=False
    if message.endswith("|-n"):
        message = message[:-3]
        negative=True
        
    inputs = PreprocessRawinput(message, negative_prompt, quality, style, quality_dict, style_dict)
    if not isinstance(inputs, dict):
        return inputs
    
    prompt = inputs["prompt"] if not negative else inputs["negative_prompt"]
    tokens = TOKENIZER(prompt).input_ids
    
    logger.debug("Get tokens: {}".format(tokens))
    
    return "接受输入 {} 的长度为: {}, 允许最大长度为: {}".format(prompt, len(tokens), max_length)

@handle_exceptions
def Text2Image(bot, 
               target_id: int, 
               message_type: str, 
               message: str, 
               api_url: str, 
               save_dir: str, 
               prefix: str, 
               negative_prompt: str="", 
               quality: str="", 
               style: str="", 
               quality_dict: dict={}, 
               style_dict: dict={}, 
               custom_width: int=1024, 
               custom_height: int=1024, 
               notice_postdata: bool=False,
               notice: bool=True, 
               return_url: bool=True):
    postdata = PreprocessRawinput(message, negative_prompt, quality, style, 
                                  quality_dict, style_dict, custom_width, custom_height, return_url)
    if not isinstance(postdata, dict):
        return postdata, "text"
    if notice:
        notice_msg = "援桌中, postdata为\n{}".format(postdata) if notice_postdata else "援桌中..."
        bot.SendMessage(notice_msg, message_type, target_id, "text")
    if not isinstance(postdata, dict):
        return postdata, "text"
    logger.debug("Get postdata: {}".format(postdata))
    
    r = requests.post(api_url, json=postdata)
    # r = requests.get("https://www.baidu.com/favicon.ico")
    if r.status_code == 200:
        logger.debug("Get image from {}".format(api_url))
        if r.headers["Content-Type"] == "application/json":
            return r.json()["url"], "image"
        return SaveImage(r.content, save_dir, prefix), "image"
    
    logger.warning("Get image failed! {}".format(r.text))
    return f"援桌失败了喵\n{r.text}", "text"

@handle_exceptions
def AutoText2Image(bot, 
                   target_id: int, 
                   message_type: str, 
                   prompt: str, 
                   api_url: str, 
                   save_dir: str, 
                   prefix: str, 
                   negative_prompt: str, 
                   quality: str, 
                   style: str, 
                   quality_dict: dict, 
                   style_dict: dict, 
                   custom_width: int=1024, 
                   custom_height: int=1024, 
                   notice: bool=False, 
                   return_url: bool=True):
    prompt = f"prompt={prompt}"
    filepath, type = Text2Image(bot, target_id, message_type, prompt, api_url, save_dir, 
                                prefix, negative_prompt, quality, style, quality_dict, style_dict, 
                                custom_width, custom_height, notice=False, return_url=return_url)
    if type == "image":
        return filepath, type
    if notice:
        bot.SendMessage(filepath, message_type, target_id, "text")