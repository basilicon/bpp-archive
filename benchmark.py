import time
from sqlalchemy import event
from app import app, db

def run_benchmark():
    app.config['TESTING'] = True
    
    # Target URLs
    urls = [
        ('/', 'Homepage'),
        ('/games', 'Game List'),
        ('/game/45', 'Game Detail (ID 45)'),
        ('/user/6', 'User Detail (ID 6)'),
        ('/users', 'Artists List'),
        ('/characters', 'Characters List'),
        ('/character/33', 'Character Detail (ID 33)'),
        ('/api/panel/random', 'Random Panel API')
    ]
    
    with app.app_context():
        client = app.test_client()
        results = []
        
        for url, description in urls:
            queries = []
            
            # Listener function to capture executed queries
            def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                queries.append(statement)
                
            # Hook listener to the engine
            event.listen(db.engine, "before_cursor_execute", before_cursor_execute)
            
            # Execute the HTTP request
            start_time = time.perf_counter()
            response = client.get(url)
            end_time = time.perf_counter()
            
            # Unhook the listener immediately
            event.remove(db.engine, "before_cursor_execute", before_cursor_execute)
            
            duration = end_time - start_time
            
            results.append({
                'url': url,
                'desc': description,
                'status_code': response.status_code,
                'queries_count': len(queries),
                'duration_ms': duration * 1000,
            })
            
        # Format results
        print(f"\n{'URL':<25} | {'Description':<25} | {'Status':<6} | {'SQL Queries':<11} | {'Time (ms)':<10}")
        print("-" * 85)
        for r in results:
            print(f"{r['url']:<25} | {r['desc']:<25} | {r['status_code']:<6} | {r['queries_count']:<11} | {r['duration_ms']:<10.2f}")


if __name__ == '__main__':
    run_benchmark()
