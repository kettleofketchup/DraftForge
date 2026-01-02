# Database

# Using UV

`uv venv`
`uv sync`
```
$ uv add ruff
Creating virtual environment at: .venv
Resolved 2 packages in 170ms
   Built example @ file:///home/user/example
Prepared 2 packages in 627ms
Installed 2 packages in 1ms
 + example==0.1.0 (from file:///home/user/example)
 + ruff==0.5.0

$ uv run ruff check
All checks passed!

$ uv lock
Resolved 2 packages in 0.33ms
$ uv sync
Resolved 2 packages in 0.70ms
````

edit dtx/models.py

python manage.py makemigrations dtx

python manage.py migrate dtx

python manage.py createsuperuser

python manage.py runserver
