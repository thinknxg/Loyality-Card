from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="care_card",
    version="1.0.0",
    description="Hospital & Pharmacy Subscription Card Program for Frappe/ERPNext",
    author="Kreatao",
    author_email="info@kreatao.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
