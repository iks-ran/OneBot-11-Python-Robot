from utils import handle_exceptions, logger
import traceback
import openai

client = openai.OpenAI(api_key="")

@handle_exceptions
def CreateChatHistory(bot,
                      cmd_name: str):
    if "chat_history" not in bot.Commands[cmd_name]:
        with bot.COMMAND_LOCK:
            commands = bot.Commands
            cmd_dict = commands[cmd_name]
            cmd_dict["chat_history"] = {}
            commands[cmd_name] = cmd_dict
            bot.Commands = commands
            logger.debug("Create chat history for command {}: {}".format(
                          cmd_name, bot.Commands[cmd_name]["chat_history"]))
    
    return bot.Commands[cmd_name]["chat_history"]

@handle_exceptions
def GenerateTargetHistory(bot, 
                          cmd_name: str,
                          message: str, 
                          target: str, 
                          chat_history: dict={}):
    chat_history = chat_history if chat_history else CreateChatHistory(bot, cmd_name)
    target_history = chat_history.get(target, [])
    if not target_history:
        chat_history[target] = target_history
        logger.debug("Create chat history for {} {}".format(target, chat_history))
    target_history.append({"role": "user", "content": message})
    logger.debug("Add user message to target chat history, {}".format(target_history))
    return target_history, chat_history

@handle_exceptions
def ToOpenAI(api_key: str, 
             chat_history: list, 
             model: str="gpt-3.5-turbo"):
    client = openai.OpenAI(api_key=api_key)
    try: 
        r = client.chat.completions.create(model=model, messages=chat_history)
        logger.debug("Finish completion: {}".format(r))
        chat_history.append({"role": "assistant", "content": r.choices[0].message.content})
        return chat_history, r.usage.total_tokens
    
    except Exception as e:
        traceback_str = traceback.format_exc()
        return_str = "Exception in `ToOpenAI`: {}\n".format(e) + \
                     "Traceback: {}".format(traceback_str)
        logger.error(return_str)
        return return_str, None

@handle_exceptions
def UpdateChatHistory(bot, 
                      target: str, 
                      cmd_name: str,
                      target_history: list=[], 
                      chat_history: dict={},
                      clear: bool=False): 
    commands = bot.Commands
    cmd_dict = commands[cmd_name]
    chat_history = chat_history if chat_history else CreateChatHistory(bot, cmd_name)
    
    if not clear:
        message = target_history[-1]["content"]
    else:
        message = "已清空喵"
        target_history = []
        logger.debug("Chat History for {} cleared!".format(target))
    
    with bot.COMMAND_LOCK:
        chat_history[target] = target_history
        cmd_dict["chat_history"] = chat_history
        commands[cmd_name] = cmd_dict
        bot.Commands = commands
    logger.debug("Update chat history, {}".format(bot.Commands[cmd_name]["chat_history"]))
    
    return message

@handle_exceptions
def Chat(bot, 
         message: str, 
         api_key: str,
         target_id: int, 
         cmd_name: str, 
         model: str="gpt-3.5-turbo", 
         chat_history: dict={}, 
         ):
    target = str(target_id)
    if message == "clear":
        UpdateChatHistory(bot, target, cmd_name, clear=True)
        return "已清空"
    openai.api_key = api_key
    logger.debug("Chat with message: {}".format(message))
    target_history, chat_history = GenerateTargetHistory(bot, cmd_name, message, target, chat_history)
    new_target_history, total_tokens = ToOpenAI(api_key, chat_history=target_history, model=model)
    if total_tokens is None:
        return new_target_history
    return UpdateChatHistory(bot, target, cmd_name, new_target_history, chat_history) + \
           f"\n|当前累计 token: {total_tokens}"

@handle_exceptions
def ConditionalChat(bot, 
                    message: str, 
                    api_key: str,
                    target_id: int, 
                    cmd_name: str, 
                    model: str="gpt-3.5-turbo", 
                    chat_history: dict={}, 
                    conditional_history: list=[]):
    target = str(target_id)
    if message == "clear":
        UpdateChatHistory(bot, target, cmd_name, clear=True)
        return "已清空喵"
    target_history, chat_history = GenerateTargetHistory(bot, cmd_name, message, target, chat_history)
    target_history = conditional_history + target_history
    new_target_history, total_tokens = ToOpenAI(api_key, chat_history=target_history, model=model)
    new_target_history = new_target_history[len(conditional_history):]
    if total_tokens is None:
        return new_target_history
    return UpdateChatHistory(bot, target, cmd_name, new_target_history, chat_history) + \
           f"\n|当前累计 token: {total_tokens}"