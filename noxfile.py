# https://nox.thea.codes/en/stable/config.html

import nox

# fail if using an external program without external=True
nox.options.error_on_external_run = True


@nox.session(
    tags=["all"],
    default=False,
)
def format(session):
    session.install("-e", ".[contrib]")
    session.run("ruff", "format", ".")
    session.run("ruff", "check", ".", "--fix")
    session.run("ruff", "check", ".", "--fix", "--select", "I")
    session.run("pyrefly", "check", ".")


@nox.session(
    tags=["all", "test"],
    default=True,
)
def test(session):
    session.install("-e", ".[test]")
    session.install("pytest-xdist")
    session.run("pytest", "-n=auto")


@nox.session(
    name="test-with-coverage",
    tags=["all", "coverage"],
    default=False,
)
def test_with_coverage(session):
    session.install("-e", ".[test]")
    session.run("coverage", "run", "-m", "pytest")
    session.run("coverage", "combine")
    session.run("coverage", "report")
    session.run("coverage", "html")


@nox.session(
    tags=["all", "build"],
    default=False,
)
def build(session):
    session.run("rm", "-rf", "build", external=True)
    session.run("rm", "-rf", "dist", external=True)
    session.install("build")
    session.run("python", "-m", "build")
