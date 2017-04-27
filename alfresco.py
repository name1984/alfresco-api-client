#!flask/bin/python

from datetime import datetime
from flask import Flask, jsonify, make_response, redirect, url_for, request
import settings
import requests
from lxml import etree
from cmislib.model import CmisClient
from cmislib.exceptions import ObjectNotFoundException, UpdateConflictException
import pdb
import sys

sys.setrecursionlimit(1500)
app = Flask(__name__)

tickets ={'RESULTADOS' :
     [
        {
            'id': 1,
            'response': None,
            'done': False,
            'time_created': False
        }
    ]
}

documents_alf = None

def is_ticket_valid():
    now = datetime.now()
    if tickets['RESULTADOS'][0]['time_created']:
        diff = now - datetime.strptime(tickets['RESULTADOS'][0]['time_created'], '%Y-%m-%d %H:%M:%S.%f')
        if diff < settings.TIME_LIFE_TICKET:
            return True
        else:
            return False
    else:
        return False


def check_ticket(element):
    if len(element.text) == settings.TICKET_LENGTH:
        return element.text
    return False


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

@app.route('/todo/api/v1.0/connection', methods=['GET'])
def connection():
    """
    :return:
    """
    opciones = {"u": settings.USERNAME_ALF, "pw": settings.PASSWORD_ALF}
    URL_REQUEST = "http://%s:%d/alfresco/service/api/login" % (settings.IP_SERVER, settings.PORT_SERVER)
    parser = etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8')

    try:
        r = requests.get(URL_REQUEST, params=opciones)
        root = etree.fromstring(bytes(r.text), parser=parser)
        ticket = check_ticket(root)

        if ticket:
            tickets['RESULTADOS'][0]['response'] = root.text
            tickets['RESULTADOS'][0]['time_created'] = str(datetime.now())
            tickets['RESULTADOS'][0]['done'] = True
            return jsonify(tickets)
        else:
            return make_response(jsonify({'error': 'Authentication Failed'}), 503)

    except:
        return make_response(jsonify({'error': 'Not connection'}), 504)

def get_repository():
    try:
        URL_CMIS = "http://%s:%d/alfresco/cmisatom" % (settings.IP_SERVER, settings.PORT_SERVER)
        client = CmisClient(URL_CMIS, settings.USERNAME_ALF, settings.PASSWORD_ALF)
        repo = client.defaultRepository
        return repo, True

    except:
        return False, make_response(jsonify({'error': 'Authentication Failed'}), 503)

def get_folder(folder_id, repo):
    try:
        folder = repo.getFolder(folder_id)
        return folder, True
    except ObjectNotFoundException:
        return False, make_response(jsonify({'error': 'Folder not found'}), 404)

def get_document_link(documents):
    URL_DOWNLOAD = "http://%s:%d/alfresco/d/d/workspace/SpacesStore" % (settings.IP_SERVER, settings.PORT_SERVER)
    i = 0
    aux_documents = None
    for document in documents:
        if not aux_documents:
            aux_documents = []
        doc_name_link = document.getProperties().get("cmis:name").replace(" ", "%20")
        doc_name = document.getProperties().get("cmis:name")
        url = "%s/%s/%s?ticket=%s" % (URL_DOWNLOAD, document.getProperties().get("alfcmis:nodeRef")[24:], doc_name_link, tickets['RESULTADOS'][0]['response'])
        aux_documents.append({'id': i, 'node': document.getProperties().get("alfcmis:nodeRef")[24:], 'name': doc_name, 'url': url})
        i += 1
    aux_documents_final = {"RESULTADOS":aux_documents}
    return aux_documents_final

@app.route('/todo/api/v1.0/document', methods=['GET'])
def get_document():
            repo, status = get_repository()
            if repo:
                folder, status = get_folder(settings.NODE_FOLDER_PORTAL, repo)
                if folder:
                    objetosRS = folder.getChildren()
                    objetos = objetosRS.getResults()
                    if is_ticket_valid():
                       documents_alf = get_document_link(objetos)
                       if documents_alf:
                           return jsonify(documents_alf)
                       else:
                           return make_response(jsonify({'error': 'Not documents'}), 404)
                    else:
                        return make_response(jsonify({'error': 'Ticket Session Expiration'}), 503)
                else:
                    return status

            else:
                return status
def update_ticket():
    opciones = {"u": settings.USERNAME_ALF, "pw": settings.PASSWORD_ALF}
    URL_REQUEST = "http://%s:%d/alfresco/service/api/login" % (settings.IP_SERVER, settings.PORT_SERVER)
    parser = etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8')

    try:
        r = requests.get(URL_REQUEST, params=opciones)
        root = etree.fromstring(bytes(r.text), parser=parser)
        ticket = check_ticket(root)

        if ticket:
            tickets['RESULTADOS'][0]['response'] = root.text
            tickets['RESULTADOS'][0]['time_created'] = str(datetime.now())
            tickets['RESULTADOS'][0]['done'] = True
            return tickets
        else:
            return {'error': 'Authentication Failed'}

    except:
        return {'error': 'Not connection'}


def get_alfresco_documents(node_folder_portal):
    repo, status = get_repository()
    if repo:
        folder, status = get_folder(node_folder_portal, repo)
        if folder:
            objetosRS = folder.getChildren()
            objetos = objetosRS.getResults()
            documents_alf = get_document_link(objetos)
            if documents_alf:
               return jsonify(documents_alf)
            else:
               return make_response(jsonify({'error': 'Not documents'}), 404)
        else:
            return status
    else:
        return status

@app.route('/todo/api/v1.0/get_documents', methods=['GET'])
def get_documentv2():
    node_folder_portal = request.args.get('node_folder_portal')
    if is_ticket_valid():
        return get_alfresco_documents(node_folder_portal)
    else:
        status = update_ticket()
        if status.has_key('error'):
            return make_response(jsonify(status), 504)
        else:
            return get_alfresco_documents(node_folder_portal)


def load_file(path):
    try:
        f = open(path, 'rb')
        return f
    except IOError:
        return False

@app.route('/todo/api/v1.0/document', methods=['POST'])
def create_document():
    try:
        if not request.json or not 'path' in request.json or not 'name' in request.json:
            abort(400)

        path_file = request.json['path']
        file_name = request.json['name']
        repo, status = get_repository()
        if repo:
            folder, status = get_folder(settings.NODE_FOLDER_UPLOAD, repo)
            if folder:
                file = load_file(path_file)
                if file:
                    document = folder.createDocument(file_name, contentFile=file)
                    file.close()
                    return make_response(jsonify({'id': 1, 'response': 'successfull',
                                                  'document_id': document.getProperties().get('alfcmis:nodeRef'),
                                                  'title': document.getProperties().get('cmis:name'), 'done': True}))
                else:
                    make_response(jsonify({'error': 'document not found'}), 404)
            else:
                return status
        else:
            return status

    except UpdateConflictException:
        return  make_response(jsonify({'error': 'create document'}), 500)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
