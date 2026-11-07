# peptibase10: administrator steps for the Microbiome Platform

For the person with sudo on peptibase10 (AlmaLinux 9.8). The platform already runs under the
account `parashn` as two systemd *user* services; the website listens on `127.0.0.1:8000`
(this machine only). These steps make it always-on and reachable over HTTPS from the lab
network / university VPN only. Nothing here opens the server to the internet.

Facts checked on the server (2026-11-07): name `peptibase10.math.biu.ac.il`, address
`132.70.2.150` (interface `eno8303`), SELinux enforcing, firewalld active, Docker present,
**something already listens on `127.0.0.1:80`**, Apache httpd is installed (unused by us),
nginx is not installed, `httpd_can_network_connect` is off.

## 0. Fill these in first (from university IT)

```bash
HOST=peptibase10.math.biu.ac.il   # or the alias IT creates, e.g. microbiome.math.biu.ac.il
SERVER_IP=132.70.2.150
LAB=<lab network range, e.g. 132.70.x.0/24>
VPN=<university VPN range>
```

Every later command uses these variables, in the same terminal.

## 1. Always-on services (survive logout and reboot)

```bash
sudo loginctl enable-linger parashn
loginctl show-user parashn -p Linger             # expect: Linger=yes
sudo restorecon -R /home/parashn                 # home is unlabeled_t today
ls -Zd /home/parashn                             # expect: ...:user_home_dir_t:...
```

## 2. The HTTPS certificate (the private key never leaves the server)

```bash
sudo openssl req -new -newkey rsa:2048 -nodes \
  -keyout /etc/pki/tls/private/$HOST.key -out /root/$HOST.csr \
  -subj "/CN=$HOST" -addext "subjectAltName=DNS:$HOST"
sudo chmod 600 /etc/pki/tls/private/$HOST.key
sudo cat /root/$HOST.csr                         # send this request to university IT
```

When IT returns the certificate (PEM, **with the full chain**, intermediate certificates included):

```bash
sudo cp <the file from IT> /etc/pki/tls/certs/$HOST.crt
sudo restorecon -v /etc/pki/tls/certs/$HOST.crt /etc/pki/tls/private/$HOST.key
sudo openssl x509 -in /etc/pki/tls/certs/$HOST.crt -noout -subject -enddate
# the certificate and the key belong together if these two lines are identical:
sudo openssl x509 -in /etc/pki/tls/certs/$HOST.crt -noout -pubkey | sha256sum
sudo openssl pkey -in /etc/pki/tls/private/$HOST.key -pubout | sha256sum
```

(If IT prefers to issue the key and certificate together: key to `/etc/pki/tls/private/$HOST.key`,
mode 600; certificate to `/etc/pki/tls/certs/$HOST.crt`.)

## 3. nginx: HTTPS on port 443, lab/VPN ranges only

```bash
sudo dnf install -y nginx
```

**Before starting it:** the default `/etc/nginx/nginx.conf` contains a `server { listen 80 ... }`
block. Port 80 is already taken on this machine (`127.0.0.1:80`), so nginx would fail to start.
Open `/etc/nginx/nginx.conf` (`sudo nano /etc/nginx/nginx.conf`), and inside `http { ... }` delete
or comment out that whole default `server { ... }` block. Keep the line
`include /etc/nginx/conf.d/*.conf;`.

```bash
sudo cp /home/parashn/microbiome-platform/deploy/nginx/microplatform.almalinux.conf /etc/nginx/conf.d/microplatform.conf
sudo sed -i -e "s/<HOSTNAME>/$HOST/g" -e "s/<SERVER_IP>/$SERVER_IP/g" \
            -e "s#<LAB_NETWORK_CIDR>#$LAB#" -e "s#<VPN_CIDR>#$VPN#" /etc/nginx/conf.d/microplatform.conf
sudo restorecon -v /etc/nginx/conf.d/microplatform.conf
grep -n "<" /etc/nginx/conf.d/microplatform.conf  # expect: no lines with <...> left
sudo setsebool -P httpd_can_network_connect 1    # lets nginx forward to 127.0.0.1:8000
sudo nginx -t                                    # expect: syntax is ok / test is successful
sudo systemctl enable --now nginx
sudo ss -ltnp | grep nginx                       # expect: 132.70.2.150:443 only
```

More ranges: add one `allow <range>;` line per range, above `deny  all;`, then `sudo nginx -t && sudo systemctl reload nginx`.

## 4. Firewall: port 443 only, only from the same ranges

```bash
sudo firewall-cmd --get-active-zones             # the zone of eno8303 (expected: public)
for RANGE in $LAB $VPN; do
  sudo firewall-cmd --permanent --zone=public \
    --add-rich-rule="rule family=\"ipv4\" source address=\"$RANGE\" port port=\"443\" protocol=\"tcp\" accept"
done
sudo firewall-cmd --reload
sudo firewall-cmd --zone=public --list-all       # "services" must NOT include https; the rich rules list the ranges
```

Do **not** add the `https` service to the zone: that would open 443 to everyone.

## 5. Tell parashn it is done

The platform's settings are then switched to "behind nginx" (trusted proxy headers, secure
cookies, the public address for result links); that needs no root.

## 6. Check

- From a computer on the lab network / VPN: `https://$HOST` opens the Microbiome Platform.
- From outside (e.g. a phone without VPN): no connection (firewall), or 403 (nginx).
- On the server: `sudo tail /var/log/nginx/microplatform.access.log` (addresses of runs are never logged).

## Undo

```bash
sudo systemctl disable --now nginx
for RANGE in $LAB $VPN; do
  sudo firewall-cmd --permanent --zone=public \
    --remove-rich-rule="rule family=\"ipv4\" source address=\"$RANGE\" port port=\"443\" protocol=\"tcp\" accept"
done
sudo firewall-cmd --reload
sudo setsebool -P httpd_can_network_connect 0
sudo loginctl disable-linger parashn
```
