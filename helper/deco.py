def randam_sleep(func):
    from time import sleep
    from random import uniform

    def _wrapper(*args, **keywords):
        sleep(uniform(0.1, 1))
        v = func(*args, **keywords)
        return v
    return _wrapper
