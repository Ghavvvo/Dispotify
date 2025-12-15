FROM node:20-alpine
WORKDIR /app


COPY package*.json ./
RUN npm install -g pnpm
RUN pnpm install


COPY . .


WORKDIR /app/leader-resolver
RUN pnpm install


WORKDIR /app


ARG VITE_API_URL
ARG VITE_STATIC_URL

ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_STATIC_URL=${VITE_STATIC_URL}


ENV CLUSTER_DNS_NAME=dispotify-cluster
ENV BACKEND_PORT=8000
ENV LEADER_ENDPOINT=/cluster/leader
ENV SERVICE_PORT=3001
ENV LEADER_CACHE_TTL=5000


RUN chmod +x /app/start.sh

EXPOSE 3000 3001
CMD ["/app/start.sh"]
