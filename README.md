# Celantur ArcGIS Examples

In a file [celantur-arcgis-example-v1.ipynb](celantur-arcgis-example-v1.ipynb) contains the example code (Currently 
POC version).

## Preparing
1. On the ArcGIS page [https://celantur.maps.arcgis.com/home/content.html](https://celantur.maps.arcgis.com/home/content.html)
   click to `New Item` button and proceed with creation of `Feature Layer`.
2. Then open that new Item, and open `Data` tab and select `Fields` sub-tab
3. Click to `Add` button (only if this field does not yet exist)
   * `Field Name`: `is_anonymized`
   * `Display Name`: `Is anonymized`
   * `Type`: `integer`
   * `Default Value`: `0`
   * Click `Add New Field`
4. Add images as attachment to points via Field Maps app. Make sure the same Feature Service Layer is specified in the Notebook code.
5. Run the code (described in [Code-running](#code-running) section)


## Code-running
Use that file as a template and follow the next steps:
1. In the section of `! CREDENTIALS !` specify your credentials accordingly
2. Go to section `Main`
   * Adjust `layer_id` uid value to the corresponding layer you want to use.
   * Adjust params to your taste (Available parameters could be found in official celantur-doc: [https://doc.celantur.com/cloud-api/api-endpoints#create-anonymization-task](https://doc.celantur.com/cloud-api/api-endpoints#create-anonymization-task))
3. Run the code


## Code Example

**The example bellow suppose to be a single script of code!**

#### ! CREDENTIALS !
```python
username = "****@celantur.com"
password = "****"
```

#### Celantur Preparation
```python
from os.path import basename
from time import sleep

import requests

host = "https://api.celantur.com/v2"


def celantur_connect(username: str, password: str) -> dict:
    payload = {
        "username": username,
        "password": password,
    }
    response = requests.post(f"{host}/signin", json=payload)
    token = response.json()["AccessToken"]
    return {"Authorization": token}


def celantur_anonymize_start(headers: dict, params: dict, *files) -> dict:
    res = {}
    for file in files:
        response = requests.post(f"{host}/task", json=params, headers=headers)
        result = response.json()
        task_id = result["task_id"]
        upload_url = result["upload_url"]
        with open(file, "rb") as fd:
            file_content = fd.read()
        requests.put(upload_url, data=file_content)
        res[task_id] = file

    return res


def celantur_anonymize_finish(headers: dict, tasks: dict, store_folder: str):
    anon_files = {}
    for tid, file in tasks.items():
        keep_checking = True
        result = None
        while keep_checking:
            response = requests.get(f"{host}/task/{tid}/status", headers=headers)
            result = response.json()
            if result["task_status"] == "done":
                keep_checking = False
            else:
                print("Waiting 5 seconds (polling)...")
                sleep(5)

        file_name = basename(file)
        response = requests.get(result["anonymized_url"])
        final_name = f"{store_folder}/anon-{file_name}"
        with open(final_name, "wb") as fd:
            fd.write(response.content)
        anon_files["tid"] = final_name
    
    return anon_files


def celantur_process_layer(layer_id, params):
    print("Processing started...")
    
    supported_content_types = ("image/jpeg", "image/png")
    feature_flag_name = "new_anonymized"
    
    layer = gis.content.get(layer_id).layers[0]

    available_attachments = layer.attachments.search()

    for attachment_object in available_attachments:
        
        featureset_id = attachment_object["PARENTOBJECTID"]
        attachment_content_type = attachment_object["CONTENTTYPE"]
        
        if attachment_content_type in supported_content_types:
            featureset = layer.query(where=f"OBJECTID={featureset_id}")
            
            if not featureset:
                continue
            
            all_features = featureset.features
            feature = all_features[0]
            
            is_anonymized = feature.attributes[feature_flag_name]
            
            if not is_anonymized:
                print(f"Anonymizing {attachment_object}\n")
                local_path = layer.attachments.download(oid=featureset_id, attachment_id=attachment_object["ID"])
                local_path = local_path[0]
                
                headers = celantur_connect(username, password)
                tasks = celantur_anonymize_start(headers, params, local_path)
                anon_files = celantur_anonymize_finish(headers, tasks, "/arcgis/home/downloads")

                for anon_file in anon_files.values():
                    layer.attachments.add(featureset_id, anon_file)
                    feature.attributes[feature_flag_name] = True
                    layer.edit_features(updates=[feature])
            else:
                print(f"Skipping (already anonymized) {attachment_object}\n")
        else:
            print(f"Skipping (non-image) {attachment_object}\n")
    
    print("Processing Finished!")
    
```

#### Main
```python

from arcgis.gis import GIS
gis = GIS("home")

# Adjust important params
celantur_process_layer(
    
    # Type: Feature Service
    layer_id="3374217d28904bf8a538ae9b4ebe93a4",
    
    params={
        "anonymization_method": "blur",
        "face": True,
        "license-plate": True,
    }
    
)

```
