FROM ubuntu:14.04
COPY remove-after.sh /usr/local/bin/remove-after
RUN \
  apt-get -y update && \
  apt-get -y install curl && \
  chmod a+x /usr/local/bin/remove-after
CMD ["/usr/local/bin/remove-after"]
