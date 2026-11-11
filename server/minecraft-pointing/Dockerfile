FROM maven:3.9.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
COPY src ./src
RUN mvn -B -q package
FROM itzg/minecraft-server:2026.10.1-java21
COPY --from=build /build/target/ciel-pointing.jar /plugins/ciel-pointing.jar
