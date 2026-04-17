FROM node:20-bullseye

WORKDIR /workspace/frontend-react

COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN npm install

EXPOSE 8000

CMD ["sh", "-lc", "npm install && npm run dev -- --host 0.0.0.0 --port 8000"]
