.PHONY: build run stop restart test logs clean

# Build the docker containers
build:
	docker-compose build

# Run the docker containers in the background
run:
	docker-compose up -d

# Stop the docker containers
stop:
	docker-compose down

# Restart the docker containers
restart: stop run

# View the logs
logs:
	docker-compose logs -f

# Run tests inside a temporary web container
# We install test dependencies on the fly since they aren't in requirements.txt
test:
	docker-compose run --rm -v $(PWD)/tests:/app/tests -v $(PWD)/pytest.ini:/app/pytest.ini web sh -c "pip install pytest pytest-asyncio httpx && pytest tests"

# Clean up docker containers, images, and volumes
clean:
	docker-compose down -v --rmi all
