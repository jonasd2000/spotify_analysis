from app import App

def main():
    app = App()
    app.parse_arguments()
    app.run()
    
if __name__ in {"__main__", "__mp_main__"}:
    main()
