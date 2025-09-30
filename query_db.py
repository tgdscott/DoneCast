import psycopg
conn = psycopg.connect(host="34.11.250.121", dbname="podcast", user="podcast", password="T3sting123")
cur = conn.cursor()
cur.execute('SELECT id, name, user_id FROM podcast')
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
