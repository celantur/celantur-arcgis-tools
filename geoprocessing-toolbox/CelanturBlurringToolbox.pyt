# -*- coding: utf-8 -*-

import arcpy
import tempfile
from arcgis.features import FeatureLayer
from os.path import basename
from time import sleep
import requests


host = "https://api.celantur.com/v2"


def celantur_connect(username: str, password: str, messages) -> dict:
    """
    Get access token for Celantur Cloud API
    """
    payload = {
        "username": username,
        "password": password,
    }
    response = requests.post(f"{host}/signin", json=payload)
    try:
        token = response.json()["AccessToken"]
        messages.addMessage(f'User {username} successfully authenticated and token received.')
        return {"Authorization": token}
    except:
        messages.addErrorMessage(f'Login error (Status {response.status_code}): {response.text}')
        raise SystemExit(-1)


def celantur_anonymize_start(headers: dict, params: dict, *files) -> dict:
    """
    Upload file to Celantur Cloud API
    """
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
    """
    Wait for processing to finish and download the anonymised file.
    """
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


def celantur_process_layer(layer, username: str, password: str, params: dict, messages):
    """
    Blur images via Celantur Cloud API
    """
    messages.addMessage("Processing started...")

    supported_content_types = ("image/jpeg", "image/png")
    feature_flag_name = "new_anonymized"

    # See https://developers.arcgis.com/python/latest/guide/working-with-feature-layers-and-features/#accessing-feature-layers-from-a-feature-layer-url
    layer = FeatureLayer(layer)

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
                messages.addMessage(f"Anonymizing {attachment_object}\n")
                local_path = layer.attachments.download(oid=featureset_id, attachment_id=attachment_object["ID"])
                local_path = local_path[0]

                headers = celantur_connect(username, password, messages)
                tasks = celantur_anonymize_start(headers, params, local_path)
                anon_files = celantur_anonymize_finish(headers, tasks, tempfile.gettempdir())

                for anon_file in anon_files.values():
                    layer.attachments.add(featureset_id, anon_file)
                    feature.attributes[feature_flag_name] = True
                    layer.edit_features(updates=[feature])
            else:
                messages.addMessage(f"Skipping (already anonymized) {attachment_object}\n")
        else:
            messages.addMessage(f"Skipping (non-image) {attachment_object}\n")

    messages.addMessage("Processing Finished!")


class Toolbox:
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Celantur Blurring Toolbox"
        self.alias = "celanturblurringtoolbox"

        # List of tool classes associated with this toolbox
        self.tools = [Tool]


class Tool:
    def __init__(self):
        """
        Define the tool (tool name is the name of the class).
        https://pro.arcgis.com/en/pro-app/latest/arcpy/geoprocessing_and_python/defining-parameters-in-a-python-toolbox.htm
        """
        self.label = "Celantur Blurring Tool"
        self.description = "Tool to connect to Celantur Cloud API and blur images"

    def getParameterInfo(self):
        """Define the tool parameters."""
        username = arcpy.Parameter(
           displayName="Celantur App username (email)",
           name="username",
           datatype="GPString",
           parameterType="Required",
           direction="Input")

        password = arcpy.Parameter(
           displayName="Celantur App password",
           name="password",
           datatype="GPStringHidden",
           parameterType="Required",
           direction="Input")

        layer = arcpy.Parameter(
           displayName="Feature Service Layer",
           name="feature_service_layer",
           datatype="GPFeatureLayer",
           parameterType="Required",
           direction="Input")

        # Default: https://celantur.maps.arcgis.com/apps/mapviewer/index.html?layers=3374217d28904bf8a538ae9b4ebe93a4
        layer.value = "https://services.arcgis.com/1SwFSrfmv5SchEGG/arcgis/rest/services/Celantur_Test_Layer/FeatureServer/0"

        return [username, password, layer]

    def isLicensed(self):
        """Set whether the tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        username = parameters[0].value
        password = parameters[1].value
        layer = parameters[2].value

        messages.addMessage(f"Username: {username}")
        messages.addMessage(f"Layer: {layer}")
        celantur_process_layer(
            str(layer), username, password,
            params={
                "anonymization_method": "blur",
                "face": True,
                "license-plate": True,
            },
            messages=messages
        )
        return

    def postExecute(self, parameters):
        """This method takes place after outputs are processed and
        added to the display."""
        return
