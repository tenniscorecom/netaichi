if __name__ == '__main__':
    import sys
    arg = sys.argv[1]

    match(arg):
        case 'init':
            from bot import db_init
            db_init()
        case 'r':
            from bot import reserve
            reserve()
        case 'k':
            from bot import komada
            komada()
        case 'o':
            from bot import oguri
            oguri()
        case _:
            print(f"不明なコマンド: {arg}（init / r / k / o のいずれか）")
