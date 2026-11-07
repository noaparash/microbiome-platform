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
VPN=<university VPN range>        # or leave empty:  VPN=
```

Every later command uses these variables, in the same terminal.

**Choosing the ranges: narrow, never a guess.**
- `LAB` = the lab's or the department's own subnet, as you know it from the department network
  (for example `132.70.x.0/24`). If you are not sure of the subnet, use a single lab computer's
  address as `x.x.x.x/32`, and add the others later ("Adding a range later" in step 3).
- **Never** a wide range such as `132.70.0.0/16` (likely the whole university, Wi-Fi and dorms
  included) or `0.0.0.0/0` (the whole internet).
- `VPN`: only the exact range from university IT. Until IT sends it, leave it empty (`VPN=`);
  steps 3 and 4 then simply skip it, and off-campus users keep using the SSH tunnel.

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

**If IT's certificate has not arrived yet:** do step 2b now and continue with steps 3 and 4; the
site works the same. When IT's certificate arrives, do "Swapping in IT's certificate" in 2b.

## 2b. Interim: a self-signed certificate (until IT's certificate arrives)

The first block of step 2 (the key and the request) must already be done, and the request sent to
IT. This signs the same request with the same key, valid for 90 days, so IT's certificate later
replaces one file and nothing else changes.

```bash
echo "subjectAltName=DNS:$HOST" | sudo tee /root/$HOST.ext
sudo openssl x509 -req -in /root/$HOST.csr -signkey /etc/pki/tls/private/$HOST.key \
  -days 90 -extfile /root/$HOST.ext -out /etc/pki/tls/certs/$HOST.crt
sudo restorecon -v /etc/pki/tls/certs/$HOST.crt /etc/pki/tls/private/$HOST.key
sudo openssl x509 -in /etc/pki/tls/certs/$HOST.crt -noout -subject -enddate -ext subjectAltName
sudo openssl x509 -in /etc/pki/tls/certs/$HOST.crt -noout -fingerprint -sha256
```

The `-subject` line should show `CN=` your `$HOST`, `subjectAltName` should show `DNS:` the same name,
and `notAfter` should be about 90 days from today. **Send the last line (the SHA-256 fingerprint) to
parashn.** It goes to the lab, so people can check that the certificate their browser warns about is
this one (browser: the "Not secure" label → certificate details → SHA-256 fingerprint).

What users see while it is in place: a one-time "Your connection is not private" warning per browser;
they click "Advanced" → "Proceed". The connection is fully encrypted. The template's HSTS header is
ignored by browsers while the certificate is self-signed, so nobody gets locked out.

**Swapping in IT's certificate** (PEM with the full chain, issued for the request from step 2):

```bash
sudo cp <the file from IT> /etc/pki/tls/certs/$HOST.crt
sudo restorecon -v /etc/pki/tls/certs/$HOST.crt
# the certificate and the key belong together if these two lines are identical:
sudo openssl x509 -in /etc/pki/tls/certs/$HOST.crt -noout -pubkey | sha256sum
sudo openssl pkey -in /etc/pki/tls/private/$HOST.key -pubout | sha256sum
sudo openssl x509 -in /etc/pki/tls/certs/$HOST.crt -noout -issuer -enddate   # issuer: the university's CA
sudo nginx -t && sudo systemctl reload nginx
```

The browser warning then disappears for everyone; nothing else changes. If IT issued a new key as
well, put it in `/etc/pki/tls/private/$HOST.key` (mode 600) before the checks.

**If IT is still slow after 90 days:** run the `openssl x509 -req` command above again, then
`sudo systemctl reload nginx` (and send parashn the new fingerprint).

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
[ -z "$VPN" ] && sudo sed -i '/<VPN_CIDR>/d' /etc/nginx/conf.d/microplatform.conf   # no VPN range yet
sudo sed -i -e "s/<HOSTNAME>/$HOST/g" -e "s/<SERVER_IP>/$SERVER_IP/g" \
            -e "s#<LAB_NETWORK_CIDR>#$LAB#" -e "s#<VPN_CIDR>#$VPN#" /etc/nginx/conf.d/microplatform.conf
sudo restorecon -v /etc/nginx/conf.d/microplatform.conf
grep -n "<" /etc/nginx/conf.d/microplatform.conf  # expect: no lines with <...> left
sudo setsebool -P httpd_can_network_connect 1    # lets nginx forward to 127.0.0.1:8000
sudo nginx -t                                    # expect: syntax is ok / test is successful
sudo systemctl enable --now nginx
sudo ss -ltnp | grep nginx                       # expect: 132.70.2.150:443 only
```

**Adding a range later** (the VPN range from IT, another lab computer, …): it must go in both
nginx and the firewall.

```bash
NEW=<the range, e.g. 10.x.0.0/16 or x.x.x.x/32>
sudo sed -i "/^ *deny  all;/i\    allow $NEW;" /etc/nginx/conf.d/microplatform.conf
grep -nE "allow|deny" /etc/nginx/conf.d/microplatform.conf   # the new allow line sits above deny
sudo nginx -t && sudo systemctl reload nginx
sudo firewall-cmd --permanent --zone=public \
  --add-rich-rule="rule family=\"ipv4\" source address=\"$NEW\" port port=\"443\" protocol=\"tcp\" accept"
sudo firewall-cmd --reload
```

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
sudo firewall-cmd --reload        # ranges added later: the same --remove-rich-rule with $NEW
sudo setsebool -P httpd_can_network_connect 0
sudo loginctl disable-linger parashn
```
