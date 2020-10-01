/*
  Prerequisite:
  Run: npm install --save form-data axios
*/

const axios = require('axios')
const FormData = require('form-data')
const fs = require('fs')

const gatewayUrl = 'https://gateway.speechlab.sg'
const email = 'YOUR_EMAIL'
const password = 'YOUR_PASSWORD'

async function login() {
  try {
    const response = await axios.post(gatewayUrl + '/auth/login', {
      email,
      password
    })

    return response.data.accessToken
  } catch (error) {
    console.log('Error when logging in')
    console.log(error)
  }
}

async function submitJob(filepath, accessToken) {
  try {
    const formData = new FormData()
    formData.append('file', fs.createReadStream(filepath))
    formData.append('lang', 'english')
    formData.append('queue', 'dhl') // this is important, you must parse 'dhl' here

    const formHeaders = formData.getHeaders()
    const response = await axios.post(gatewayUrl + '/speech', formData, {
      headers: {
        ...formHeaders,
        'Authorization': 'Bearer ' + accessToken,
      },
      maxContentLength: Infinity,
    })

    return response.data

    
  } catch (error) {
    console.log('Error when submitting job')
    console.log(error)
  }
}

async function main() {
  const accessToken = await login()
  const response = await submitJob('audio.wav', accessToken)

  console.log(response)
  /* If success will print:
    {
      result: null,
      status: 'created',
      formats: [ 'stm', 'srt', 'TextGrid' ],
      sampling: '16khz',
      lang: 'english',
      name: 'Note',
      _id: '5f15525eda78980029c3e6b1',
      queue: 'dhl',
      createdAt: '2020-07-20T08:14:22.631Z'
    }
  */
}

main()

