# django-cacheops
Django-cacheops is a powerful ORM-level caching library for Django. It provides automatic and granular caching for querysets and invalidates cache on model changes.

## Installation

1. Install the package:

```
pip install django-cacheops
```

2. Add `'cacheops'` to your `INSTALLED_APPS` in `settings.py`.

3. Configure the cache backend (Redis is required):

```
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
```

4. Add `CACHEOPS_REDIS` and `CACHEOPS` settings to your `settings.py`:

```
CACHEOPS_REDIS = {
    'host': '127.0.0.1',
    'port': 6379,    # default Redis port
    'db': 1,         # separate DB for cacheops
    'socket_timeout': 3,
}

CACHEOPS = {
    # Enable caching for your tournament-related models
    'app.tournament': {'ops': 'all', 'timeout': 60*60},
    'app.team': {'ops': 'all', 'timeout': 60*60},
    'app.customuser': {'ops': 'all', 'timeout': 60*60},
    'app.draft': {'ops': 'all', 'timeout': 60*60},
    'app.game': {'ops': 'all', 'timeout': 60*60},
    # ...add more as needed
}

CACHEOPS_DEGRADE_ON_FAILURE = True
```

5. Run Redis server if not already running.

6. Restart your Django app.

## Usage

- Querysets for configured models will be cached automatically.
- Cache is invalidated on model save/delete.
- You can use `.cache()` on querysets for custom cache control.

See https://github.com/Suor/django-cacheops for more details.
