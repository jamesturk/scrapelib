FROM python:3.9

WORKDIR /opt/scrapeshell
RUN pip install readline ipython lxml cssselect

COPY . /opt/scrapeshell
RUN pip install poetry

RUN poetry install
ENTRYPOINT ["scrapeshell"]
