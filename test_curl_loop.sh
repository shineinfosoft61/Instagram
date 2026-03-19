#!/bin/bash

# Test curl command 5 times in a loop
echo "Testing curl command 5 times..."
echo "================================"

for i in {1..2000}
do
    echo "Run #$i:"
    curl --location 'https://vidssave.com/api/proxy' \
    --header 'accept: */*' \
    --header 'accept-language: en-GB,en-US;q=0.9,en;q=0.8,gu;q=0.7' \
    --header 'content-type: application/json' \
    --header 'origin: https://vidssave.com' \
    --header 'priority: u=1, i' \
    --header 'referer: https://vidssave.com/yt' \
    --header 'sec-ch-ua: "Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"' \
    --header 'sec-ch-ua-mobile: ?0' \
    --header 'sec-ch-ua-platform: "Linux"' \
    --header 'sec-fetch-dest: empty' \
    --header 'sec-fetch-mode: cors' \
    --header 'sec-fetch-site: same-origin' \
    --header 'user-agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36' \
    --data '{
        "url": "/media/parse",
        "data": {
            "origin": "cache",
            "link": "https://www.youtube.com/watch?v=enY83Li8_ps"
        },
        "token": ""
    }'
    
    echo -e "\n----------------------------------------"
    sleep 1  # Wait 1 second between requests
done

echo "Test completed!"
