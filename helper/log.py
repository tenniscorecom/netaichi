
from logging import Logger, getLogger, StreamHandler, FileHandler, Formatter
from logging import DEBUG, INFO
from pathlib import Path
from datetime import datetime


class AppLogger:

    logger: Logger = None
    FILE_NAME = 'app'
    CONSOLE_LEVEL = DEBUG
    FILE_LEVEL = INFO

    def __init__(self, name='app', console_level=DEBUG, file_level=INFO):
        self.FILE_NAME = name
        self.CONSOLE_LEVEL = console_level
        self.FILE_LEVEL = file_level
        path = Path('logs') / self.FILE_NAME
        path.mkdir(exist_ok=True, parents=True)
        formatter = Formatter('%(asctime)s, %(levelname)s, %(message)s')
        self.logger = getLogger(self.FILE_NAME)
        self.logger.setLevel(self.CONSOLE_LEVEL)
        self.__set_console_handler(formatter)
        self.__set_file_handler(formatter)

    def info(self, message) -> None:
        self.logger.info(message)

    def debug(self, message) -> None:
        self.logger.debug(message)

    def warning(self, message) -> None:
        self.logger.warning(message)

    def error(self, message) -> None:
        self.logger.error(message)

    def __set_console_handler(self, formatter: Formatter) -> None:
        handler = StreamHandler()
        handler.setFormatter(formatter)
        handler.setLevel(self.CONSOLE_LEVEL)
        self.logger.addHandler(handler)

    def __set_file_handler(
            self,
            formatter: Formatter) -> None:
        file_name = datetime.now().strftime('%Y_%m_%d')
        handler = FileHandler(f"./logs/{self.FILE_NAME}/{file_name}.log")
        handler.setLevel(self.FILE_LEVEL)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
