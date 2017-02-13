
all: clean
	docker build -t horngame:latest .
	docker run -t -p 8081:8081 horngame

.PHONY: clean superclean
clean: 
	if [ ! -z "$$(docker ps -a -q --filter ancestor=horngame --format="{{.ID}}")" ]; then docker rm $$(docker stop $$(docker ps -a -q --filter ancestor=horngame --format="{{.ID}}")); fi

superclean:
	if [ ! -z "$$(docker ps -a -q --format="{{.ID}}")" ]; then docker rm $$(docker stop $$(docker ps -a -q --format="{{.ID}}")); fi
	if [ ! -z "$$(docker images -a -q --format="{{.ID}}")" ]; then docker rmi $$(docker images -a -q --format="{{.ID}}"); fi
