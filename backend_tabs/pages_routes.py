from flask import render_template


def register_pages_routes(app):
    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/config")
    def config_page():
        return render_template("config.html")

    @app.get("/products")
    def products_page():
        return render_template("products.html")
