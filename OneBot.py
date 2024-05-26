from utils import (handle_exceptions_for_methods, 
                   instantiate_from_config, 
                   is_request_success, 
                   logger)
from timeout_decorator import timeout
from omegaconf import OmegaConf
from fastapi import FastAPI
from copy import deepcopy
import multiprocessing
import threading
import traceback
import requests
import logging
import inspect
import signal
import uvicorn
import time
import json
import sys
import os

@handle_exceptions_for_methods
class OneBot:
    def __init__(self, 
                 AdminID: int,
                 HttpPostHost: str,
                 HttpPostPort: int,
                 HttpAPIURL: str,
                 Logger: logging.Logger,
                 Notice: str="",
                 RetryCount: int=3,
                 ManualCommands: dict={},
                 AutoCommands: dict={},
                 PostCommands: dict={},
                 **kwargs):
        
        self.AdminID = AdminID
        self.Notice = Notice
        self.RetryCount = RetryCount
        self.HttpPostHost = HttpPostHost
        self.HttpPostPort = HttpPostPort
        self.HttpAPIURL = HttpAPIURL
        self.Logger = Logger
    
        if kwargs != {}:
            logger.warning("Unrecognized parameters: {}".format(kwargs))
        
        logger.info("AdminID: {}".format(self.AdminID))
        logger.info("HttpPostHost: {}".format(self.HttpPostHost))
        logger.info("HttpPostPort: {}".format(self.HttpPostPort))
        logger.info("HttpAPIURL: {}".format(self.HttpAPIURL))
        logger.info("Notice: {}".format(self.Notice))
        logger.info("RetryCount: {}".format(self.RetryCount))
        
        self._init_commands(ManualCommands, AutoCommands, PostCommands)
        self._init_auto_commands()
        self._init_post_commands()
        self._init_receiver()
        self._init_server()
        
        logger.info("OneBot is initialized")
        
    def _init_commands(self, 
                       ManualCommands: dict ,
                       AutoCommands: dict,
                       PostCommands: dict):
        Manager = multiprocessing.Manager()
        Commands = Manager.dict()
        self.COMMAND_LOCK = Manager.Lock()
        OriginalCommands = {**ManualCommands, **AutoCommands, **PostCommands}
        CommandFunctions = {}
        
        for cmd_type, commands in {"Manual": ManualCommands, "Auto": AutoCommands, 
                                   "Post": PostCommands}.items():
            for cmd_name in commands:
                cfg = deepcopy(commands[cmd_name])
                func, params, extra_params = instantiate_from_config(cfg)
                cmd = {"CommandType": cmd_type, "target": commands[cmd_name]["target"]}
                if params:
                    cmd.update({"params": params})
                if extra_params:
                    cmd.update(extra_params)
                CommandFunctions[cmd_name] = func
                Commands[cmd_name] = cmd
            
        self.Commands = Commands
        self.CommandFunctions = CommandFunctions
        self.OrginalCommands = OriginalCommands
        logger.info("Commands: \n{}".format(json.dumps(dict(self.Commands), indent=2)))
        
    def _init_auto_commands(self):
        commands = self.Commands
        for cmd_name in commands:
            cmd_dict = commands[cmd_name]
            if cmd_dict["CommandType"] == "Auto":
                living_params = {"running_process": 0, "last_runtime": 0}
                cmd_dict["living_params"] = living_params
            commands[cmd_name] = cmd_dict
        self.Commands = commands
        logger.info("Auto commands: \n{}".format(
                         json.dumps({key: dict(value) for key, value in self.Commands.items() 
                                     if value["CommandType"] == "Auto"}, indent=2))) 
        
    def _init_post_commands(self):
        def signal_handler(sig, frame):
            logger.info("Received signal {}, prepare to exit".format(sig))
            self.HandlePostCommands()
            logger.info("Post commands handled, exit")
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        logger.info("Post commands: \n{}".format(
                         json.dumps({key: dict(value) for key, value in self.Commands.items() 
                                     if value["CommandType"] == "Post"}, indent=2)))
        
    @timeout(30)
    def _init_receiver(self):
        for i in range(self.RetryCount):
            request_url = self.HttpAPIURL + "/get_status"
            # if True: 
            r = requests.get(request_url)
            if self.is_request_success(r):
                # if True: 
                if r.json().get("data", {}).get("online", False):
                    logger.info("Receiver is online")
                    if self.Notice:
                        self.SendMessage(self.Notice, "private", self.AdminID, "text")
                    return
                
            logger.warning("Receiver is not online: {}".format(r.text))
            logger.warning("Retry in 1 second")
            time.sleep(1)
            
        logger.error("Receiver is not online after {} retries, exit".format(self.RetryCount))
        sys.exit(1)
        
    def _init_server(self):
        app = FastAPI()
        @app.post("/")
        async def read_event(event: dict):
            logger.debug("Receive Event :{}".format(event))
            if "message_id" in event:
                self.HandleMessage(event)
    
        def run_server():
            uvicorn.run(app, host=self.HttpPostHost, port=self.HttpPostPort)
        threading.Thread(target=run_server, daemon=True).start()
        
    def is_admin(self, 
                 target_id: int):
        return target_id == self.AdminID
        
    def clean_cache(self):
        for i in range(self.RetryCount):
            request_url = self.HttpAPIURL + "/clean_cache"
            # if True: 
            r = requests.get(request_url)
            if self.is_request_success(r):
                logger.info("Cache cleaned")
                return "缓存已清空"
            logger.warning("Failed to clean cache: {}".format(r.text))
            logger.warning("Retry in 1 second")
            time.sleep(1)
        logger.warning("Failed to clean cache after {} retries".format(self.RetryCount))
        return "清空缓存失败"
            
    def is_request_success(self, 
                           response: requests.Response):
        if is_request_success(response):
            if response.json()["status"] == "ok":
                return True
            
        return False
    
    def get_config(self):
        cfg = {"AdminID": self.AdminID,
               "HttpPostHost": self.HttpPostHost,
               "HttpPostPort": self.HttpPostPort,
               "HttpAPIURL": self.HttpAPIURL,
               "Notice": self.Notice,
               "RetryCount": self.RetryCount,
               "ManualCommands": {},
               "AutoCommands": {},
               "PostCommands": {}}
        
        for cmd_name in self.Commands.keys():
            CommandType = self.Commands[cmd_name]["CommandType"]
            target = self.Commands[cmd_name]["target"]
            params = self.Commands[cmd_name].get("params", {})
            # original_params = self.OrginalCommands[cmd_name].get("params", {})
            extra_params = self.Commands[cmd_name].get("extra_params", {})
            shared_params = extra_params.pop("shared_params", {})
            auto_params = shared_params.pop("auto_params", {})
            cmd_cfg = {"target": target}
            if params:
                cmd_cfg.update({"params": params})
            for param in params:
                if param in shared_params:
                    shared_params.pop(param)
            if shared_params:
                extra_params.update({"shared_params": shared_params})
            if auto_params:
                extra_params.update({"auto_params": auto_params})
            if extra_params:
                cmd_cfg.update({"extra_params": extra_params})
            cfg[CommandType + "Commands"].update({cmd_name: cmd_cfg})
        
        return OmegaConf.create(cfg)
    
    def PreprocessMessage(self, 
                          message: int|str|list|dict, 
                          type: str|list):
        if isinstance(message, list):
            if isinstance(type, str):
                return [self.PreprocessMessage(m, type) for m in message]
            else:
                return [self.PreprocessMessage(m, t) for m, t in zip(message, type)]
        
        if isinstance(message, dict):
            return [self.PreprocessMessage(m, t) for m, t in message.items()]
        
        if type == "text":
            if message == "":
                message = " "
            return {"type": "text", "data": {"text": message}}
        if type in ["image", "record", "video", "file"]:
            if os.path.exists(message):
                return {"type": type, "data": {"file": message}}
            elif message.startswith("http://") or message.startswith("https://"):
                return {"type": type, "data": {"file": message, "url": message}}
            else:
                return {"type": "text", "data": {"text": "文件不存在: {}".format(message)}}
        if type == "at":
            return {"type": "at", "data": {"qq": message}}
        if type in ["face", "reply", "forward", "node"]:
            return {"type": type, "data": {"id": message}}
        if type in ["dice", "shake", "rps"]:
            return {"type": type, "data": {}}
            
        logger.warning("Temporary not support type to preprocess: {}".format(type))
        return {"type": "text", "data": {"text": "当前不支持的消息类型: [{}:{}]".format(type, message)}}
    
    @timeout(120)
    def SendMessage(self, 
                    message: int|str|list|dict, 
                    message_type: str, 
                    target_id: int, 
                    type: str|list):
        message = self.PreprocessMessage(message, type)
        if message is not None:
            postdata = {"message_type": message_type, "message": message}
            postdata.update({"group_id": target_id} if message_type == "group" else {"user_id": target_id})
            for i in range(self.RetryCount): 
                # if True:
                r = requests.post(self.HttpAPIURL + "/send_msg", json=postdata)
                if self.is_request_success(r):
                    logger.info("Send message to [{}:{}]: {}".format(
                                     message_type, target_id, message))
                    return
                logger.warning("Failed to send message: {}".format(r.text))
                logger.warning("Retry in 1 second")
                time.sleep(1)
            logger.warning("Failed to send message after {} retries".format(self.RetryCount))
    
    def HandleMessage(self, 
                      meta_message: dict):
        logger.debug("Receive message: \n{}".format(json.dumps(meta_message, indent=2)))
        
        message_type = meta_message.get("message_type", None)
        message_list = meta_message.get("message", [])
        if not (message_type and message_list):
            logger.warning("Not a message event")
            return
        message_id = meta_message["message_id"]
        sender_id = meta_message["sender"]["user_id"]
        group_id = meta_message.get("group_id", "")
        type = message_list[0]["type"]
        if not (type in ["text", "face", "image", "record", "video", "at", "rps", "dice", "shake", 
                         "poke", "share", "contact", "location", "music", "reply", "forward", "node",
                         "xml", "json"]):
            logger.warning("Type unsupported: {}".format(type))
            return
        message = meta_message["raw_message"]
        nick_name = meta_message["sender"]["nickname"]
        target_id = group_id if message_type == "group" else sender_id
        
        logger.info("{}{}({}): {}".format(f"[Group({group_id})] - " if group_id else "", 
                                               nick_name, sender_id, message))
        
        splited_message = message.split("|", 1)
        if len(splited_message) > 1 and splited_message[0] in self.Commands:
            process = multiprocessing.Process(target=self.HandleCommand, 
                                                args=(splited_message[0], splited_message[1], 
                                                    message_type, sender_id, target_id, message_id))
            process.start()
            logger.debug("Start a process for command '{}'".format(splited_message[0]))
                
    def HandleCommand(self, 
                      cmd_name: str, 
                      message: str, 
                      message_type: str, 
                      sender_id: int,
                      target_id: int, 
                      message_id: int, 
                      send_message: bool=True):
        cmd_func = self.CommandFunctions[cmd_name]
        # cmd_func, *_ = instantiate_from_config(deepcopy(self.Commands[cmd_name]))
        params = self.Commands[cmd_name].get("params", {})
        extra_params = self.Commands[cmd_name].get("extra_params", {})
        shared_params_dict = extra_params.pop("shared_params", {})
        
        for cmd in shared_params_dict:
            for param in shared_params_dict[cmd]:
                p = self.Commands.get(cmd, {}).get("params", {}).get(param, "Not Found")
                if p == "Not Found":
                    logger.warning("Shared param '{}' not found for command '{}'".format(param, cmd))
                    return
                params.update({param: p})
        params.update(extra_params)
                
        all_params = {"bot": self, "message": message, "message_type": message_type, "cmd_name": cmd_name,
                      "sender_id": sender_id, "target_id": target_id, "message_id": message_id, **params}
        input_params = {}
        sig = inspect.signature(cmd_func)
        for param in sig.parameters:
            if param in all_params:
                input_params.update({param: all_params[param]})
            
        result = cmd_func(**input_params)
        type = extra_params.get("type", "text")
        message = None
        if result is not None:
            if isinstance(result, tuple):
                message, type = result[0], result[1]
            else:
                message = result
            if send_message:
                self.SendMessage(message, message_type, target_id, type)
        return message, message_type, target_id, type
            
    def HandleAutoCommand(self, 
                          cmd_name: str):
        message_type = self.Commands[cmd_name]["extra_params"].get("message_type", "")
        target_id = self.Commands[cmd_name]["extra_params"].get("target_id", 0)
        send = self.Commands[cmd_name]["extra_params"].get("send", False)
        message, *_, type  = self.HandleCommand(cmd_name, "", message_type, 0, target_id, 0, send_message=False)
        with self.COMMAND_LOCK:
            commands = self.Commands
            cmd_dict = commands[cmd_name]
            living_params = cmd_dict["living_params"]
            living_params["running_process"] = max(0, living_params["running_process"] - 1)
            commands[cmd_name] = cmd_dict
            self.Commands = commands
        logger.debug("Finish a process for auto command '{}', now {} / {} process is alive".format(
                           cmd_name, self.Commands[cmd_name]["living_params"]["running_process"], 
                           self.Commands[cmd_name]["extra_params"].get("num_process", 1)))
        if message is not None and send:
            self.SendMessage(message, message_type, target_id, type)
    
    def HandleAutoCommands(self):
        with self.COMMAND_LOCK:
            commands = self.Commands
            for cmd_name in commands:
                if commands[cmd_name]["CommandType"] == "Auto":
                    cmd_dict = commands[cmd_name]
                    living_params = cmd_dict["living_params"]
                    if not cmd_dict["extra_params"]["auto_params"]["run"]:
                        continue
                    now = time.time()
                    interval = now - living_params["last_runtime"]
                    if interval < cmd_dict["extra_params"]["auto_params"]["min_execution_interval"]:
                        continue
                    if interval > cmd_dict["extra_params"]["auto_params"]["longest_idle_interval"]:
                        living_params["running_process"] = 0
                        logger.warning("Auto command {} hasn't run for {}s, reset".format(cmd_name, interval))
                    num_process = cmd_dict["extra_params"]["auto_params"].get("num_process", 1)
                    running_process = max(0, living_params["running_process"])
                    for i in range (num_process - running_process):
                        process = multiprocessing.Process(target=self.HandleAutoCommand, 
                                                        args=(cmd_name,))
                        running_process += 1
                        living_params["running_process"] = running_process
                        living_params["last_runtime"] = time.time()
                        process.start()
                        logger.debug("Start a process for auto command '{}', now {} / {} process is alive".format(
                                          cmd_name, living_params["running_process"], num_process))
                    cmd_dict["living_params"] = living_params
                    commands[cmd_name] = cmd_dict
            self.Commands = commands
            
    def HandlePostCommands(self):
        for cmd_name in self.Commands.keys():
            if self.Commands[cmd_name]["CommandType"] == "Post":
                logger.info("Handle post command: {}".format(cmd_name))
                self.HandleCommand(cmd_name, "", "", 0, 0, 0, False)
            
    def run(self):
        
        while True:
            try:
                self.HandleAutoCommands()
                time.sleep(1)
            except Exception as e:
                logger.error("Exception in 'run': {}".format(e))
                traceback_str = traceback.format_exc()
                logger.error("Traceback: {}".format(traceback_str))
                time.sleep(1)
            