from dataclasses import dataclass


@dataclass(slots=True)
class Paper:
    doi: str
    title: str
    journal: str
    pub_date: str
    author: str
    link: str
    abstract: str
    abstract_source: str
