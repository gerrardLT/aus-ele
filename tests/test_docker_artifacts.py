import os
import unittest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class DockerArtifactTests(unittest.TestCase):
    def test_compose_and_docker_files_exist(self):
        expected_paths = [
            "docker-compose.yml",
            ".dockerignore",
            ".env.docker.example",
            "Dockerfile.backend",
            "web/Dockerfile",
            "deploy/nginx/default.conf",
            "docs/deployment/baota-docker.md",
        ]

        for relative_path in expected_paths:
            with self.subTest(path=relative_path):
                self.assertTrue(os.path.exists(os.path.join(REPO_ROOT, relative_path)))

    def test_compose_uses_configurable_project_ports_and_named_volumes(self):
        compose_path = os.path.join(REPO_ROOT, "docker-compose.yml")
        with open(compose_path, "r", encoding="utf-8") as compose_file:
            content = compose_file.read()

        self.assertIn("${WEB_HOST_PORT:-18080}", content)
        self.assertIn("${API_HOST_PORT:-18085}", content)
        self.assertIn("${REDIS_HOST_PORT:-16379}", content)
        self.assertIn("backend:", content)
        self.assertIn("web:", content)
        self.assertIn("redis:", content)
        self.assertIn("./data:/app/data", content)

    def test_web_dockerfile_and_lockfile_do_not_pin_unreachable_mirror(self):
        dockerfile_path = os.path.join(REPO_ROOT, "web", "Dockerfile")
        lockfile_path = os.path.join(REPO_ROOT, "web", "package-lock.json")
        gitignore_path = os.path.join(REPO_ROOT, ".gitignore")

        with open(dockerfile_path, "r", encoding="utf-8") as dockerfile:
            dockerfile_content = dockerfile.read()
        with open(lockfile_path, "r", encoding="utf-8") as lockfile:
            lockfile_content = lockfile.read()
        with open(gitignore_path, "r", encoding="utf-8") as gitignore:
            gitignore_content = gitignore.read()

        self.assertIn("ARG NPM_REGISTRY", dockerfile_content)
        self.assertIn("!web/package-lock.json", gitignore_content)
        self.assertNotIn("registry.npmmirror.com", lockfile_content)


if __name__ == "__main__":
    unittest.main()
