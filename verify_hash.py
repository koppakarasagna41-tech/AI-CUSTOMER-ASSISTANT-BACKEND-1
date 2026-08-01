from passlib.context import CryptContext
h = '$pbkdf2-sha256$29000$BSDE.P./975X6t37P8c4Rw$LJxc87.I6re85SPct40YW70KPl5qLfENChkWf6MwHAU'
ctx = CryptContext(schemes=['bcrypt','pbkdf2_sha256'], deprecated='auto')
print('repr', repr(h))
print('identify', ctx.identify(h))
print('verify', ctx.verify('rasagna@A3', h))
