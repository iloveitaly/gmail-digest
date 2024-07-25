lint:
	poetry run black .
	poetry run isort .
#poetry run autoflake --exclude=chowmetrics --exclude=migrations --imports=decouple,rich -i -r .
	poetry run autoflake --imports=decouple,rich -i -r .
	poetry run flake8 .
	poetry run deptry .